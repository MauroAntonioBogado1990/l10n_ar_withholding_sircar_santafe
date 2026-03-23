# -*- coding: utf-8 -*-
from odoo import models, api, fields
from collections import defaultdict
from odoo.tools.misc import formatLang, format_date, get_lang
from odoo.exceptions import ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)

class AccountMoveInherit(models.Model):
    """
    Extensión del modelo de Facturas (account.move) para incluir 
    la lógica de cálculo automático de Percepciones de Ingresos Brutos (Santa Fe).
    """
    _inherit = "account.move"

    def calculate_perceptions(self):
        """
        Método principal que decide si se debe aplicar la percepción de Santa Fe
        y actualiza las líneas de la factura con el impuesto correspondiente.
        """
        if self.move_type in ['out_invoice', 'out_refund']:
            
            if not self.invoice_date:
                self.invoice_date = date.today()

            if self.invoice_line_ids:
                
                if self.partner_id:
                    _logger.info("=== SANTA FE: Partner %s (ID: %s)", self.partner_id.name, self.partner_id.id)
                    _logger.info("=== SANTA FE: Cantidad de alicuotas en padron: %s", len(self.partner_id.alicuot_per_santafe_ids))
                    
                    if len(self.partner_id.alicuot_per_santafe_ids) > 0:
                        
                        imp_per_santafe = self.company_id.tax_per_santafe
                        _logger.info("=== SANTA FE: Impuesto configurado en compania: %s (ID: %s)", imp_per_santafe.name if imp_per_santafe else 'NO CONFIGURADO', imp_per_santafe.id if imp_per_santafe else 'N/A')
                        
                        if not imp_per_santafe:
                            _logger.info("=== SANTA FE: SIN impuesto configurado, saliendo sin aplicar percepcion")
                            return super().calculate_perceptions()
                        for alic in self.partner_id.alicuot_per_santafe_ids:
                            _logger.info("=== SANTA FE DEBUG: effective_date_from: %s, effective_date_to: %s, a_per: %s, type_contr_insc: %s, alta_baja: %s, padron_activo: %s",
                                alic.effective_date_from,
                                alic.effective_date_to,
                                alic.a_per,
                                alic.type_contr_insc,
                                alic.alta_baja,
                                alic.padron_activo,
                            )
                        new_amount = self.partner_id.get_amount_alicuot_santafe('per', self.invoice_date)
                        _logger.info("=== SANTA FE: Alicuota obtenida del padron: %s%% para fecha %s", new_amount, self.invoice_date)
                        
                        imp_per_santafe.amount = new_amount        
                        
                        for iline in self.invoice_line_ids:
                            _tiene_precepcion = False

                            for tax in iline.tax_ids:
                                if str(imp_per_santafe.id) == str(tax.id)[-2:]:
                                    _tiene_precepcion = True
                            
                            _logger.info("=== SANTA FE: Linea '%s' - Ya tiene percepcion: %s - Amount impuesto: %s", iline.name, _tiene_precepcion, imp_per_santafe.amount)
                            
                            if not _tiene_precepcion and imp_per_santafe.amount > 0:
                                iline.write({'tax_ids': [(4, imp_per_santafe.id)]})
                                _logger.info("=== SANTA FE: Percepcion AGREGADA a linea '%s'", iline.name)

                        for lac in self.line_ids:
                            if lac.account_id.id == self.partner_id.property_account_receivable_id.id:
                                
                                if self.move_type == 'out_invoice':
                                    if self.currency_id.name != 'ARS':
                                        debit_tmp = sum(self.line_ids.mapped('credit'))
                                        lac.write({'debit' : debit_tmp})
                                    else:
                                        lac.write({'debit' : self.amount_total})
                                
                                elif self.move_type == 'out_refund':
                                    if self.currency_id.name != 'ARS':
                                        credit_tmp = sum(self.line_ids.mapped('debit'))
                                        lac.write({'credit' : credit_tmp})
                                    else:
                                        lac.write({'credit' : self.amount_total})
                    else:
                        _logger.info("=== SANTA FE: Partner %s NO tiene alicuotas en padron de Santa Fe", self.partner_id.name)
                else:
                    _logger.info("=== SANTA FE: Factura sin partner asignado")
            else:
                _logger.info("=== SANTA FE: Factura sin lineas de producto")
        else:
            _logger.info("=== SANTA FE: Tipo de movimiento '%s' no aplica para percepcion", self.move_type)

        return super(AccountMoveInherit, self).calculate_perceptions()
    
    #agregado nueva funcion 
    def get_amount_alicuot_santafe(self, type_alicuot, date):
        self.ensure_one()
        amount_calculated = 0.00

        if type_alicuot == 'per':
            alicuot = self.alicuot_per_santafe_ids.filtered(
                lambda l: l.effective_date_from <= date and l.effective_date_to >= date
            )
            if alicuot:
                line = alicuot[0]

                # Exento → no aplica percepción
                if line.type_contr_insc == 'E':
                    return 0.0

                # Porcentaje general de la compañía (ej: 3.5)
                porcentaje_general = float(self.env.company.l10n_ar_santafe_porcentaje_general or 0.0)

                coeficiente = float(line.coeficiente or 0.0)  # ← campo nuevo
                alicuota_per = float(line.a_per or 0.0)       # porcentaje del padrón (ej: 1.5)

                if line.type_contr_insc == 'CM':
                    # CM: coeficiente * tax_per_santafe(porcentaje_general) * alicuota_per
                    amount_calculated = coeficiente * porcentaje_general * alicuota_per

                elif line.type_contr_insc == 'CL':
                    # CL: coeficiente * alicuota_per
                    amount_calculated = coeficiente * alicuota_per

        elif type_alicuot == 'ret':
            alicuot = self.alicuot_ret_santafe_ids.filtered(
                lambda l: l.effective_date_from <= date and l.effective_date_to >= date
            )
            if alicuot:
                line = alicuot[0]
                if line.type_contr_insc == 'E':
                    return 0.0
                amount_calculated = float(line.a_ret or 0.0)

        return amount_calculated