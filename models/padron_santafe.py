# # -*- coding: utf-8 -*-
# from odoo import models, fields, api
# import logging
# _logger = logging.getLogger(__name__)

# class Padron(models.Model):
#     _name = 'santafe.padron'


#     name = fields.Char('CUIT')
#     publication_date = fields.Date('Fecha de publicacion')
#     effective_date_from = fields.Date('Fecha de vigencia desde')
#     effective_date_to = fields.Date('Fecha de vigencia hasta')
#     type_alicuot = fields.Selection([
#         ('P', 'Percepcion'),
#         ('R', 'Retencion')
#     ], 'Tipo', required = True)
#     type_contr_insc = fields.Selection([
#         ('CM', 'Convenio Multilatera'),
#         ('CL', 'Contribuyente Local'),
#         ('E', 'Exento'),
#     ], 'Tipo')
#     alta_baja = fields.Selection([
#         ('S', 'Se incorpora al padron'),
#         ('N', 'No incorpora al padron'),
#         ('B', 'Baja')
#     ], 'Alta/Baja')
#     cambio = fields.Selection([
#         ('S', 'Cambio al anterior'),
#         ('N', 'Sin cambios'),
#         ('B', 'Baja')
#     ], 'Cambio')
#     a_per = fields.Float('Alicuota-Percepcion')
#     a_ret = fields.Float('Alicuota-Retencion')
#     nro_grupo_perc = fields.Char('Nro Grupo Percepcion')
#     nro_grupo_ret = fields.Char('Nro Grupo Retencion')
#     #agregado de campo coeficiente Mauro
#     coeficiente = fields.Float('Coeficiente', digits=(16, 4))

#     @api.model
#     def create(self, vals):
#         padron = super(Padron, self).create(vals)
#         partner = self.env['res.partner'].search([('vat','=',padron.name),('parent_id','=',False)],limit=1)
#         if len(partner)>0:

#             if padron.type_alicuot == 'R':
#                 for alicuota in partner.alicuot_ret_santafe_ids:
#                     if alicuota.padron_activo == True:
#                         alicuota.padron_activo = False
#                 partner.sudo().update({'alicuot_ret_santafe_ids' : [(0, 0, {
#                     'partner_id': partner.id, 
#                     'publication_date': padron.publication_date,
#                     'effective_date_from': padron.effective_date_from,
#                     'effective_date_to': padron.effective_date_to,
#                     'type_contr_insc': padron.type_contr_insc,
#                     'alta_baja': padron.alta_baja,
#                     'cambio': padron.cambio,
#                     'a_ret': padron.a_ret,
#                     'nro_grupo_ret': padron.nro_grupo_ret,
#                     'padron_activo': True
#                 })]})
#             elif padron.type_alicuot == 'P':
#                 for alicuota in partner.alicuot_per_santafe_ids:
#                     if alicuota.padron_activo == True:
#                         alicuota.padron_activo = False
#                 partner.sudo().update({'alicuot_per_santafe_ids' : [(0, 0, {
#                     'partner_id': partner.id, 
#                     'publication_date': padron.publication_date,
#                     'effective_date_from': padron.effective_date_from,
#                     'effective_date_to': padron.effective_date_to,
#                     'type_contr_insc': padron.type_contr_insc,
#                     'alta_baja': padron.alta_baja,
#                     'cambio': padron.cambio,
#                     'a_per': padron.a_per,
#                     'nro_grupo_per': padron.nro_grupo_perc,
#                     'padron_activo': True
#                 })]})
#         return padron
    
#     def write(self, variables):
#         if 'publication_date' in variables or 'effective_date_from' in variables or 'effective_date_to' in variables or 'alta_baja' in variables or 'a_per' in variables or 'a_ret' in variables:
#             res = super(Padron, self).write(variables)
#             partner = self.env['res.partner'].search([('vat','=',self.name),('parent_id','=',False)],limit=1)
#             if len(partner)>0:

#                 if self.type_alicuot == 'R':
#                     for alicuota in partner.alicuot_ret_santafe_ids:
#                         if alicuota.padron_activo == True:
#                             alicuota.padron_activo = False
#                     partner.alicuot_ret_santafe_ids = [(0, 0, {
#                         'partner_id': partner.id, 
#                         'publication_date': self.publication_date,
#                         'effective_date_from': self.effective_date_from,
#                         'effective_date_to': self.effective_date_to,
#                         'type_contr_insc': self.type_contr_insc,
#                         'alta_baja': self.alta_baja,
#                         'cambio': self.cambio,
#                         'a_ret': self.a_ret,
#                         'nro_grupo_ret': self.nro_grupo_ret,
#                         'padron_activo': True
#                     })]
#                 elif self.type_alicuot == 'P':
#                     for alicuota in partner.alicuot_per_santafe_ids:
#                         if alicuota.padron_activo == True:
#                             alicuota.padron_activo = False
#                     partner.alicuot_per_santafe_ids = [(0, 0, {
#                         'partner_id': partner.id, 
#                         'publication_date': self.publication_date,
#                         'effective_date_from': self.effective_date_from,
#                         'effective_date_to': self.effective_date_to,
#                         'type_contr_insc': self.type_contr_insc,
#                         'alta_baja': self.alta_baja,
#                         'cambio': self.cambio,
#                         'a_per': self.a_per,
#                         'nro_grupo_per': self.nro_grupo_perc,
#                         'padron_activo': True
#                     })]
#             return res
        
#         return super(Padron, self).write(variables)


    
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Padron(models.Model):
    _name = 'santafe.padron'
    _description = 'Padrón de Retenciones y Percepciones Santa Fe'

    name = fields.Char('CUIT', index=True) # Agregamos index=True para acelerar búsquedas
    publication_date = fields.Date('Fecha de publicación')
    effective_date_from = fields.Date('Fecha de vigencia desde')
    effective_date_to = fields.Date('Fecha de vigencia hasta')
    type_alicuot = fields.Selection([
        ('P', 'Percepción'),
        ('R', 'Retención')
    ], 'Tipo', required=True, index=True)
    
    # Se suman 'D' y 'C' que son los valores nativos que trae el CSV
    type_contr_insc = fields.Selection([
        ('CM', 'Convenio Multilateral'),
        ('CL', 'Contribuyente Local'),
        ('E', 'Exento'),
        ('D', 'Directo (Local)'),
        ('C', 'Convenio (CM)'),
    ], 'Tipo')
    
    alta_baja = fields.Selection([
        ('S', 'Se incorpora al padrón'),
        ('N', 'No incorpora al padrón'),
        ('B', 'Baja')
    ], 'Alta/Baja')
    cambio = fields.Selection([
        ('S', 'Cambio al anterior'),
        ('N', 'Sin cambios'),
        ('B', 'Baja')
    ], 'Cambio')
    
    a_per = fields.Float('Alícuota-Percepción')
    a_ret = fields.Float('Alícuota-Retención')
    nro_grupo_perc = fields.Char('Nro Grupo Percepción')
    nro_grupo_ret = fields.Char('Nro Grupo Retención')
    coeficiente = fields.Float('Coeficiente', digits=(16, 4))

    @api.model_create_multi
    def create(self, vals_list):
        padrons = super(Padron, self).create(vals_list)
        self._update_partner_alicuotas(padrons)
        return padrons

    def write(self, vals):
        res = super(Padron, self).write(vals)
        campos_criticos = ['publication_date', 'effective_date_from', 'effective_date_to', 'alta_baja', 'a_per', 'a_ret']
        if any(campo in vals for campo in campos_criticos):
            self._update_partner_alicuotas(self)
        return res

    def _update_partner_alicuotas(self, padrons):
        """Método auxiliar para actualizar los partners de forma optimizada"""
        Partner = self.env['res.partner'].sudo()
        # Buscamos todos los partners afectados de una sola vez
        cuil_list = padrons.mapped('name')
        partners = Partner.search([('vat', 'in', cuil_list), ('parent_id', '=', False)])
        partner_dict = {p.vat: p for p in partners if p.vat}

        for padron in padrons:
            partner = partner_dict.get(padron.name)
            if not partner:
                continue

            vals_alicuota = {
                'partner_id': partner.id, 
                'publication_date': padron.publication_date,
                'effective_date_from': padron.effective_date_from,
                'effective_date_to': padron.effective_date_to,
                'type_contr_insc': padron.type_contr_insc,
                'alta_baja': padron.alta_baja,
                'cambio': padron.cambio,
                'padron_activo': True
            }

            if padron.type_alicuot == 'R':
                # Desactivar anteriores
                activas = partner.alicuot_ret_santafe_ids.filtered('padron_activo')
                if activas:
                    activas.write({'padron_activo': False})
                
                vals_alicuota.update({'a_ret': padron.a_ret, 'nro_grupo_ret': padron.nro_grupo_ret})
                partner.write({'alicuot_ret_santafe_ids': [(0, 0, vals_alicuota)]})
                
            elif padron.type_alicuot == 'P':
                # Desactivar anteriores
                activas = partner.alicuot_per_santafe_ids.filtered('padron_activo')
                if activas:
                    activas.write({'padron_activo': False})
                
                vals_alicuota.update({'a_per': padron.a_per, 'nro_grupo_per': padron.nro_grupo_perc})
                partner.write({'alicuot_per_santafe_ids': [(0, 0, vals_alicuota)]})