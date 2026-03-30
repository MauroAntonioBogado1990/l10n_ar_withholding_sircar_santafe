# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class AccountPaymentGroupInherit(models.Model):
    """
    Extensión del grupo de pagos (account.payment.group).
    Este modelo agrupa varias facturas y varios métodos de pago (efectivo, cheque, retenciones).
    """
    _inherit = "account.payment.group"

    def compute_withholdings(self):
        """
        Esta función se activa al presionar el botón de 'Calcular Retenciones'.
        Busca si corresponde aplicar una retención de Tucumán y genera el comprobante.
        """
        # Primero ejecuta la lógica estándar de Odoo/Localización
        res = super(AccountPaymentGroupInherit, self).compute_withholdings()
        
        for rec in self:
            # 1. VERIFICACIÓN: ¿El proveedor está en el padrón de Santa Fe?
            if len(rec.partner_id.alicuot_ret_santafe_ids) > 0:
                
                # 2. BUSCAR ALÍCUOTA: Obtiene el porcentaje de retención según la fecha del pago
                retencion = rec.partner_id.get_amount_alicuot_santafe('ret', rec.payment_date)

                # 3. CÁLCULO DE LA BASE: Sumamos los montos "Netos" (sin IVA) de las facturas que estamos pagando
                amount_untaxed_total_invs = 0
                for invs in self.debt_move_line_ids:
                    # Si la factura es en dólares u otra moneda, la convierte a pesos (ARS)
                    if invs.move_id.currency_id.name != 'ARS':
                        amount_untaxed_total_invs += invs.move_id.amount_untaxed * invs.move_id.invoice_currency_rate
                    else:
                        # Si es en pesos, la suma directamente
                        amount_untaxed_total_invs += invs.move_id.amount_untaxed

                # Sumamos también si hay pagos a cuenta (adelantos) que permitan retenciones
                amount_untaxed_total_invs += rec.withholdable_advanced_amount
                
                # 4. MONTO FINAL: Base imponible multiplicada por el porcentaje (ej. 3% / 100)
                _amount_ret_iibb = amount_untaxed_total_invs * (retencion / 100)

                # 5. CONFIGURACIÓN TÉCNICA: Buscamos en el sistema los "papeles" necesarios
                # Buscamos el método de pago tipo 'Retención'
                _payment_method = self.env.ref(
                    'l10n_ar_withholding_automatic.'
                    'account_payment_method_out_withholding')
                
                # Buscamos un diario contable (Banco o Caja) para registrar el movimiento
                _journal = self.env['account.journal'].search([
                    ('company_id', '=', rec.company_id.id),
                    ('outbound_payment_method_line_ids.payment_method_id', '=', _payment_method.id),
                    ('type', 'in', ['cash', 'bank']),
                ], limit=1)

                # Buscamos el impuesto específico de retención configurado en Odoo
                _imp_ret = self.env['account.tax'].search([
                    ('type_tax_use', '=', rec.partner_type),
                    ('company_id', '=', rec.company_id.id),
                    ('withholding_type', '=', 'partner_iibb_padron'),
                    ('tax_tucuman_ret', '=', True)], limit=1)
                
                # 6. LIMPIEZA: Si ya existía un cálculo previo de esta retención para este pago,
                # lo borramos para no duplicarlo (por si el usuario tocó el botón dos veces).
                payment_withholding = self.env['account.payment'].search([
                    ('payment_group_id', '=', rec.id),
                    ('tax_withholding_id', '=', _imp_ret.id),
                ], limit=1)

                if payment_withholding:
                    payment_withholding.unlink()

                # 7. CREACIÓN DEL COMPROBANTE: Si el porcentaje es mayor a 0, creamos la línea de pago
                if len(_imp_ret) == 0:
                    return res
                
                if retencion > 0:
                    # Se añade un nuevo 'Pago' al grupo, que es el certificado de retención
                    rec.payment_ids = [(0, 0, {
                        'name': '/',
                        'partner_id': rec.partner_id.id,
                        'payment_type': 'outbound', # Salida de dinero (hacia el estado)
                        'journal_id': _journal.id,
                        'tax_withholding_id': _imp_ret.id,
                        'payment_method_description': 'Retencion IIBB SIRCAR Santa Fe',
                        'payment_method_id': _payment_method.id,
                        'date': rec.payment_date,
                        'destination_account_id': rec.partner_id.property_account_payable_id.id,
                        'amount': _amount_ret_iibb,
                        'withholding_base_amount': amount_untaxed_total_invs
                    })]

                # 8. AJUSTE CONTABLE (Truco técnico):
                # Odoo por defecto quiere mandar el dinero a la cuenta del Banco.
                # Este bloque "engaña" al sistema por un segundo para que la contabilidad 
                # use la cuenta específica del Impuesto (Retenciones a pagar) en vez de la del Banco.
                line_ret = rec.payment_ids.filtered(lambda r: r.tax_withholding_id.id == _imp_ret.id)
                line_tax_account = line_ret.move_id.line_ids.filtered(lambda r: r.credit > 0)
                account_imp_ret = _imp_ret.invoice_repartition_line_ids.filtered(lambda r: len(r.account_id) > 0)
                
                if len(account_imp_ret) > 0:
                    # Guardamos la cuenta original del diario
                    cuenta_anterior = line_ret.move_id.journal_id.default_account_id
                    # Cambiamos temporalmente a la cuenta del impuesto
                    line_ret.move_id.journal_id.default_account_id = account_imp_ret.account_id
                    # Asignamos la cuenta al asiento
                    line_tax_account.account_id = account_imp_ret.account_id
                    # Devolvemos el diario a su cuenta original para no romper nada más
                    line_ret.move_id.journal_id.default_account_id = cuenta_anterior

        return res
