# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
import logging
_logger = logging.getLogger(__name__)



class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    def get_amount_alicuot_santafe(self, type_alicuot, date):
        self.ensure_one()
        amount_calculated = 0.00

        def _to_fraction(val):
            try:
                v = float(val or 0.0)
            except Exception:
                return 0.0
            # si viene como 1.5 (porcentaje) -> convertir a fracción 0.015
            if v > 1:
                return v / 100.0
            return v

        # Porcentaje general configurado en la compañia (se normaliza a fracción)
        porcentaje_general = float(self.env.company.l10n_ar_santafe_porcentaje_general or 0.0)
        if type_alicuot == 'per':
            # Percepciones (RG 116/10): coeficiente * (0.5 si CM else 1) * porcentaje_general
            alicuot = self.alicuot_per_santafe_ids.filtered(
                lambda l: l.effective_date_from <= date and l.effective_date_to >= date
            )
            if alicuot:
                line = alicuot[0]
                if line.type_contr_insc == 'E':
                    return 0.0
                coeficiente_frac = _to_fraction(line.a_per)
                factor = 0.5 if line.type_contr_insc == 'CM' else 1.0
                amount_fraction = coeficiente_frac * factor * porcentaje_general
                # retornamos porcentaje (ej: 1.5)
                amount_calculated = amount_fraction * 100.0

        elif type_alicuot == 'ret':
            # Retenciones (RG 176/10): usar el porcentaje del archivo acreditan (a_ret)
            alicuot = self.alicuot_ret_santafe_ids.filtered(
                lambda l: l.effective_date_from <= date and l.effective_date_to >= date
            )
            if alicuot:
                line = alicuot[0]
                if line.type_contr_insc == 'E':
                    return 0.0
                # a_ret normalmente viene como porcentaje (ej 1.5)
                amount_calculated = float(line.a_ret or 0.0)

        return amount_calculated

    alicuot_ret_santafe_ids = fields.One2many(
        'partner.padron.santafe.ret',
        'partner_id',
        'Alicuotas Retencion',
    )
    alicuot_per_santafe_ids = fields.One2many(
        'partner.padron.santafe.per',
        'partner_id',
        'Alicuotas Percepcion',
    )

class ResPartnerAlicuotRet(models.Model):
    _name = 'partner.padron.santafe.ret'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
    )
    publication_date = fields.Date('Fecha de publicacion')
    effective_date_from = fields.Date('Vigencia desde')
    effective_date_to = fields.Date('Vigencia hasta')
    type_contr_insc = fields.Selection([
        ('CM', 'Convenio Multilatera'),
        ('CL', 'Contribuyente Local'),
        ('E', 'Exento'),
        ('D', 'Directo (Local)'),   # ← AGREGADO
        ('C', 'Convenio (CM)'),     # ← AGREGADO
    ], 'Tipo')
    alta_baja = fields.Selection([
        ('S', 'Se incorpora al padron'),
        ('N', 'No incorpora al padron'),
        ('B', 'Baja')
    ], 'Alta/Baja')
    cambio = fields.Selection([
        ('S', 'Cambio al anterior'),
        ('N', 'Sin cambios'),
        ('B', 'Baja')
    ], 'Cambio')
    a_ret = fields.Float('Alicuota-Retencion')
    nro_grupo_ret = fields.Char('Nro Grupo Retencion')
    padron_activo = fields.Boolean('Activo')
    coeficiente = fields.Float('Coeficiente', digits=(16, 4))

    @api.model_create_multi
    def create(self, vals_list):
        # CORREGIDO: vals_list es una lista de diccionarios
        for vals in vals_list:
            parent = self.env['res.partner'].search([('id','=',int(vals['partner_id'])),('parent_id','=',False)],limit=1)
            for alicuota in parent.alicuot_ret_santafe_ids:
                if alicuota.padron_activo == True:
                    alicuota.padron_activo = False
            
            vals['padron_activo'] = True
        
        recs = super(ResPartnerAlicuotRet, self).create(vals_list)
        return recs

class ResPartnerAlicuotPer(models.Model):
    _name = 'partner.padron.santafe.per'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
    )
    publication_date = fields.Date('Fecha de publicacion')
    effective_date_from = fields.Date('Vigencia desde')
    effective_date_to = fields.Date('Vigencia hasta')
    type_contr_insc = fields.Selection([
        ('CM', 'Convenio Multilatera'),
        ('CL', 'Contribuyente Local'),
        ('E', 'Exento'),
        ('D', 'Directo (Local)'),   # ← AGREGADO
        ('C', 'Convenio (CM)'),     # ← AGREGADO
    ], 'Tipo')
    alta_baja = fields.Selection([
        ('S', 'Se incorpora al padron'),
        ('N', 'No incorpora al padron'),
        ('B', 'Baja')
    ], 'Alta/Baja')
    cambio = fields.Selection([
        ('S', 'Cambio al anterior'),
        ('N', 'Sin cambios')
    ], 'Cambio')
    a_per = fields.Float('Alicuota-Percepcion')
    nro_grupo_per = fields.Char('Nro Grupo Percepcion')
    padron_activo = fields.Boolean('Activo')
    coeficiente = fields.Float('Coeficiente', digits=(16, 4))

    @api.model_create_multi
    def create(self, vals_list):
        # CORREGIDO: vals_list es una lista de diccionarios
        for vals in vals_list:
            parent = self.env['res.partner'].search([('id','=',int(vals['partner_id'])),('parent_id','=',False)],limit=1)
            for alicuota in parent.alicuot_per_santafe_ids:
                if alicuota.padron_activo == True:
                    alicuota.padron_activo = False
            
            vals['padron_activo'] = True
        
        recs = super(ResPartnerAlicuotPer, self).create(vals_list)
        return recs