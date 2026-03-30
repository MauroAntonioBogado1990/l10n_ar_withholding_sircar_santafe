   
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
        padrons = super().create(vals_list)
        if not self.env.context.get('skip_partner_update'):
            self._update_partner_alicuotas(padrons)
        return padrons

    def write(self, vals):
        res = super().write(vals)
        campos_criticos = ['publication_date', 'effective_date_from',
                        'effective_date_to', 'alta_baja', 'a_per', 'a_ret']
        if not self.env.context.get('skip_partner_update'):
            if any(campo in vals for campo in campos_criticos):
                self._update_partner_alicuotas(self)
        return res

    def _update_partner_alicuotas(self, padrons):
        Partner = self.env['res.partner'].sudo()
        cuil_list = padrons.mapped('name')  # ya normalizados sin guiones

        # Buscar partners tanto con CUIT normalizado como con guiones
        def _with_guiones(cuit):
            if len(cuit) == 11:
                return f"{cuit[0:2]}-{cuit[2:10]}-{cuit[10]}"
            return cuit

        cuil_list_guiones = [_with_guiones(c) for c in cuil_list]

        partners = Partner.search([
            '|',
            ('vat', 'in', cuil_list),
            ('vat', 'in', cuil_list_guiones),
            ('parent_id', '=', False),
        ])

        # Mapa normalizado → partner
        partner_dict = {}
        for p in partners:
            if p.vat:
                norm = ''.join(filter(str.isdigit, p.vat))
                partner_dict[norm] = p

        for padron in padrons:
            partner = partner_dict.get(padron.name)
            if not partner:
                continue
            cambio_val = padron.cambio if padron.cambio in ('S', 'N', 'B') else False
            vals_alicuota = {
                'partner_id':          partner.id,
                'publication_date':    padron.publication_date,
                'effective_date_from': padron.effective_date_from,
                'effective_date_to':   padron.effective_date_to,
                'type_contr_insc':     padron.type_contr_insc,
                'alta_baja':           padron.alta_baja,
                'cambio':              cambio_val,
                'padron_activo':       True,
            }

            if padron.type_alicuot == 'R':
                activas = partner.alicuot_ret_santafe_ids.filtered('padron_activo')
                if activas:
                    activas.write({'padron_activo': False})
                vals_alicuota.update({
                    'a_ret': padron.a_ret,
                    'nro_grupo_ret': padron.nro_grupo_ret,
                })
                partner.write({'alicuot_ret_santafe_ids': [(0, 0, vals_alicuota)]})

            elif padron.type_alicuot == 'P':
                activas = partner.alicuot_per_santafe_ids.filtered('padron_activo')
                if activas:
                    activas.write({'padron_activo': False})
                vals_alicuota.update({
                    'a_per': padron.a_per,
                    'nro_grupo_per': padron.nro_grupo_perc,
                })
                partner.write({'alicuot_per_santafe_ids': [(0, 0, vals_alicuota)]})