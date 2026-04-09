# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class SircarRegimenes(models.Model):
    _name = 'sircar.regimenes'
    _description = 'Regimenes de SIRCAR'

    name = fields.Char('Nombre')
    jurisdiccion = fields.Many2one('res.country.state','Jurisdicción')
    n_jur = fields.Char('Nº Jurisdicción')
    n_reg = fields.Char('Regimen')
    vigente = fields.Selection([('si', 'Si'),('no','No')],'Vigente?')
    desde = fields.Char('Desde')
    hasta = fields.Char('Hasta')
    id_tipo = fields.Selection([('R', 'Retencion'),('P','Percepcion')],'Id Tipo')
    desc = fields.Char('Descripcion')

    @api.model
    def create(self, vars):
        vars['name'] = vars['n_jur'] + ' - ' + vars['n_reg'] + ' - ' + vars['desc'] 
        return super(SircarRegimenes, self).create(vars)
    