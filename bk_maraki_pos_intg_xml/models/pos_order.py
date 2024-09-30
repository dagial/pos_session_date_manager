from odoo import api, fields, models, tools, _
from lxml import etree
import base64
import os
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    xml_file = fields.Binary('Invoice XML File', readonly=True)
    # xml_filename = fields.Char('XML Filename')

    def action_pos_order_paid(self):
        result = super(PosOrder, self).action_pos_order_paid()
        pos_config = self.env['bk.pos.xml_dump'].search([
            ('pos_config_id', '=', self.config_id.id),
            ('allow_inv_xml', '=', True)
        ])

        path_list = []
        for address in pos_config.xml_dump_paths:
            for line in address:
                if os.path.exists(line.path):
                    path_list.append(line.path)

        if len(path_list):
            self.generate_invoice_xml(path_list)
        else:
            _logger.warning("No valid paths found for XML dumping.")

        return result

    def generate_invoice_xml(self, address_line):
        for order in self:
            try:
                # Create the root element
                before, sep, number = order.name.partition('/')
                root = etree.Element("Invoice")
                etree.SubElement(root, "Invoice_Type").text = "Invoice"
                etree.SubElement(root, "Reference_Number").text = number
                etree.SubElement(root, "Invoice_Date").text = order.date_order.strftime('%d.%m.%Y')
                etree.SubElement(root, "Customer_Code").text = order.partner_id.ref or ""
                etree.SubElement(root, "Customer_Name").text = order.partner_id.name or "Walking Customer"
                etree.SubElement(root, "Customer_TIN").text = order.partner_id.vat or ""
                etree.SubElement(root, "Payment_Type").text = 'Cash'
                etree.SubElement(root, "Invoice_DiscOrAdd_Amount").text = "{:.2f}".format(
                    order.amount_total - sum(line.price_subtotal for line in order.lines))

                for line in order.lines:
                    item = etree.SubElement(root, "Line_Items")
                    etree.SubElement(item, "Item_ID").text = line.product_id.barcode or ""
                    etree.SubElement(item, "Item_Description").text = line.product_id.name
                    etree.SubElement(item, "Item_Quantity").text = str(line.qty)
                    etree.SubElement(item, "Item_UOM").text = line.product_id.uom_id.name
                    etree.SubElement(item, "Item_Unit_Price").text = "{:.2f}".format(line.price_unit)
                    etree.SubElement(item, "Item_Tax_Percent").text = "{:.2f}".format(
                        sum(t.amount for t in line.tax_ids))
                    etree.SubElement(item, "Item_DiscOrAdd_Amount").text = "{:.2f}".format(line.discount or 0.0)

                # Convert the XML tree to a string
                tree = etree.ElementTree(root)
                xml_str = etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding="UTF-8")
                # print(xml_str)
                xml_filename = f"invoice_{order.id}.xml"
                file_written = False
                for each_path in address_line:
                    if os.path.exists(each_path):
                        try:
                            file_path = os.path.join(each_path, xml_filename)
                            with open(file_path, 'wb') as file:
                                file.write(xml_str)
                            file_written = True
                        except OSError as e:
                            _logger.error(f"Failed to write XML file to {each_path}: {e}")
                            continue  # Try next path if one fails

                if not file_written:
                    _logger.warning(f"No valid path available to write XML file for order {order.id}")

                # Update the order record with the XML file
                order.write({
                    'xml_file': base64.b64encode(xml_str),
                    # 'xml_filename': xml_filename
                })

            except Exception as e:
                _logger.error(f"Failed to generate XML for order {order.id}: {e}")
