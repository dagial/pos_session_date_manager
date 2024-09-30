from odoo import models, fields


class PosShopConfig(models.Model):
    _inherit= "pos.config"

    pos_xml_dump= fields.One2many("bk.pos.xml_dump","id",help="related xml damp locations")