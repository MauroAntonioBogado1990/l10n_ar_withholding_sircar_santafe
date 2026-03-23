# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class AccountPaymentGroupInherit(models.Model):
    _inherit = "account.payment.group"

    def compute_withholdings(self):
        # 1. Ejecuta la lógica estándar primero
        res = super(AccountPaymentGroupInherit, self).compute_withholdings()
        
        for rec in self:
            # === CAMBIO CLAVE: Quitamos el IF de len(alicuot_ids) para permitir el castigo del 5% ===
            
            # 2. BUSCAR ALÍCUOTA: Nuestra función ya devuelve 5.0 si no está en padrón
            retencion = rec.partner_id.get_amount_alicuot_santafe('ret', rec.payment_date)

            # 3. CÁLCULO DE LA BASE (Neto de facturas)
            amount_untaxed_total_invs = 0
            for invs in rec.debt_move_line_ids:
                if invs.move_id.currency_id.name != 'ARS':
                    amount_untaxed_total_invs += invs.move_id.amount_untaxed * invs.move_id.invoice_currency_rate
                else:
                    amount_untaxed_total_invs += invs.move_id.amount_untaxed

            # Sumar pagos a cuenta (adelantos)
            amount_untaxed_total_invs += rec.withholdable_advanced_amount

            # 4. BUSCAR IMPUESTO ESPECÍFICO (Necesario para la limpieza y creación)
            _imp_ret = self.env['account.tax'].search([
                ('type_tax_use', '=', rec.partner_type),
                ('company_id', '=', rec.company_id.id),
                ('tax_santafe_ret', '=', True)], limit=1)

            if not _imp_ret:
                _logger.warning("=== SANTA FE: No se encontró el impuesto marcado con 'tax_santafe_ret'")
                continue

            # 5. VALIDACIÓN DE MÍNIMO NO IMPONIBLE (Novedad 2026)
            minimo_santafe = rec.company_id.l10n_ar_santafe_minimo_retencion or 650000.0

            if amount_untaxed_total_invs < minimo_santafe:
                _logger.info("=== SANTA FE: Base %s menor al mínimo %s. Limpiando retenciones previas.", 
                             amount_untaxed_total_invs, minimo_santafe)
                
                # Limpieza: Si existía una retención y el monto bajó del mínimo, la borramos
                payment_withholding = self.env['account.payment'].search([
                    ('payment_group_id', '=', rec.id),
                    ('tax_withholding_id', '=', _imp_ret.id),
                ], limit=1)
                if payment_withholding:
                    payment_withholding.unlink()
                
                continue # Salta al siguiente proveedor

            # 6. CREACIÓN O ACTUALIZACIÓN DEL COMPROBANTE
            _amount_ret_iibb = amount_untaxed_total_invs * (retencion / 100)

            # Buscamos si ya existe la línea para actualizarla o borrarla
            payment_withholding = self.env['account.payment'].search([
                ('payment_group_id', '=', rec.id),
                ('tax_withholding_id', '=', _imp_ret.id),
            ], limit=1)

            if payment_withholding:
                payment_withholding.unlink()

            if retencion > 0:
                # Datos técnicos para el pago
                _payment_method = self.env.ref('l10n_ar_withholding_automatic.account_payment_method_out_withholding')
                _journal = self.env['account.journal'].search([
                    ('company_id', '=', rec.company_id.id),
                    ('outbound_payment_method_line_ids.payment_method_id', '=', _payment_method.id),
                    ('type', 'in', ['cash', 'bank']),
                ], limit=1)

                # Generamos el certificado
                rec.payment_ids = [(0, 0, {
                    'name': '/',
                    'partner_id': rec.partner_id.id,
                    'payment_type': 'outbound',
                    'journal_id': _journal.id,
                    'tax_withholding_id': _imp_ret.id,
                    'payment_method_description': 'Retencion IIBB SIRCAR Santa Fe',
                    'payment_method_id': _payment_method.id,
                    'date': rec.payment_date,
                    'destination_account_id': rec.partner_id.property_account_payable_id.id,
                    'amount': _amount_ret_iibb,
                    'withholding_base_amount': amount_untaxed_total_invs
                })]

                # 7. AJUSTE CONTABLE (Truco de cuenta de impuesto)
                line_ret = rec.payment_ids.filtered(lambda r: r.tax_withholding_id.id == _imp_ret.id)
                line_tax_account = line_ret.move_id.line_ids.filtered(lambda r: r.credit > 0)
                account_imp_ret = _imp_ret.invoice_repartition_line_ids.filtered(lambda r: r.account_id)
                
                if line_tax_account and account_imp_ret:
                    cuenta_anterior = line_ret.move_id.journal_id.default_account_id
                    line_ret.move_id.journal_id.default_account_id = account_imp_ret[0].account_id
                    line_tax_account.account_id = account_imp_ret[0].account_id
                    line_ret.move_id.journal_id.default_account_id = cuenta_anterior

        return res