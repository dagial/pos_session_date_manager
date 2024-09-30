from odoo import models, fields


class BkPosXmlDump(models.Model):
    _name = 'bk.pos.xml_dump'
    _rec_name = 'pos_config_id'

    pos_config_id = fields.Many2one('pos.config', string='PoS Config', help="An Existing POS")
    allow_inv_xml = fields.Boolean(string="Allow XML Dumping", help="Allow this pos transaction to be converted in xml format")
    xml_dump_paths = fields.One2many('pos.xml.dump_path', 'pos_ids', string="XML Dump Paths")

    _sql_constraints = [
        ('unique_pos_config_id', 'unique(pos_config_id)', 'This PoS is already in the listing.'),
    ]


class PosXmlDumpPath(models.Model):
    _name = 'pos.xml.dump_path'
    _description = 'POS XML Dump Path'
    _rec_name = 'pos_ids'

    pos_ids = fields.Many2one('bk.pos.xml_dump', string="PoS")
    path = fields.Char(string="Path", required=True)
