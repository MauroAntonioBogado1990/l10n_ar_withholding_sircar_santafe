# -*- coding: utf-8 -*-
# Licencia AGPL-3.0 o posterior.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, timedelta
from dateutil import relativedelta
import base64
import logging
import json

_logger = logging.getLogger(__name__)

class AccountExportSantafe(models.Model):
    """
    Esta clase representa una herramienta para exportar archivos de impuestos 
    específicos de la provincia de Santa Fe (Argentina). 
    Su objetivo es recopilar datos de retenciones y percepciones para generar 
    archivos de texto (.txt) que se presentan ante los entes recaudadores.
    """
    _name = 'account.export.santafe'
    _description = 'Exportación de archivos fiscales - Santa Fe'

    # --- CAMPOS DE CONFIGURACIÓN Y FILTROS ---
    name = fields.Char('Nombre')  # Identificador o título del reporte (ej. "Exportación Mayo 2023")
    date_from = fields.Date('Fecha desde')  # Fecha de inicio del periodo a exportar
    date_to = fields.Date('Fecha hasta')    # Fecha de fin del periodo a exportar

    # --- CAMPOS DE TEXTO (Almacenan el contenido "en crudo") ---
    # Estos campos guardan el texto que se escribirá dentro de los archivos .txt
    export_santafe_data_ret = fields.Text('Contenidos archivo SANTAFE RET', default='') # Datos de Retenciones
    export_santafe_data_per = fields.Text('Contenidos archivo SANTAFE PER', default='') # Datos de Perceptions
    export_santafe_data_nc = fields.Text('Contenidos archivo SANTAFE NC PER', default='') # Datos de Notas de Crédito
    export_santafe_data = fields.Text('Contenidos archivo SANTAFE', default='') # Datos generales o genéricos

    # Relación con el impuesto específico de retención de Santa Fe configurado en el sistema
    tax_withholding = fields.Many2one('account.tax', 'Imp. de ret utilizado', 
                                      domain=[('tax_santafe_ret', '=', True)]) 
  
    @api.depends('export_santafe_data')
    def _compute_files_generic(self):
        for rec in self:
            rec.export_santafe_filename = 'PERCECIONESRETPER.txt'
            rec.export_santafe_file = base64.b64encode(
                rec.export_santafe_data.encode('ISO-8859-1')
            )

    # Campos que almacenan el archivo físico y su nombre (basados en la función de arriba)
    export_santafe_file = fields.Binary('Archivo SANTAFE', compute=_compute_files_generic)
    export_santafe_filename = fields.Char('Nombre Archivo SANTAFE', compute=_compute_files_generic)
   
    @api.depends('export_santafe_data_nc')
    def _compute_files_nc(self):
        for rec in self:
            rec.export_santafe_filename_nc = 'NCFACTPERC.txt'
            rec.export_santafe_file_nc = base64.b64encode(
                rec.export_santafe_data_nc.encode('ISO-8859-1')
            )
    # Campos para el archivo de Notas de Crédito
    export_santafe_file_nc = fields.Binary('Archivo NC', compute=_compute_files_nc)
    export_santafe_filename_nc = fields.Char('Nombre Archivo NC', compute=_compute_files_nc)
    
    @api.depends('export_santafe_data_ret')
    def _compute_files_ret(self):
        """
        Convierte el contenido de Retenciones en un archivo descargable (.txt).
        """
        for rec in self:
            rec.export_santafe_filename_ret = _('Santafe_ret_%s_%s.txt') % (str(rec.date_from), str(rec.date_to))
            rec.export_santafe_file_ret = base64.encodestring(rec.export_santafe_data_ret.encode('ISO-8859-1'))

    # Campos para el archivo de Retenciones
    export_santafe_file_ret = fields.Binary('Archivo Retenciones', compute=_compute_files_ret)
    export_santafe_filename_ret = fields.Char('Nombre Archivo Retenciones', compute=_compute_files_ret)

    #AGREGADO
    export_santafe_data_retper = fields.Text('Contenidos RETPER', default='')

    @api.depends('export_santafe_data_retper')
    def _compute_files_retper(self):
        for rec in self:
            rec.export_santafe_filename_retper = 'RETPER.txt'
            rec.export_santafe_file_retper = base64.b64encode(
                (rec.export_santafe_data_retper or '').encode('ISO-8859-1')
            )

    export_santafe_file_retper = fields.Binary('Archivo RETPER', compute=_compute_files_retper)
    export_santafe_filename_retper = fields.Char('Nombre Archivo RETPER', compute=_compute_files_retper)
    
   
    @api.depends('export_santafe_data_per')
    def _compute_files_per(self):
        for rec in self:
            rec.export_santafe_filename_per = 'DATOSPERC.txt'
            rec.export_santafe_file_per = base64.b64encode(
                rec.export_santafe_data_per.encode('ISO-8859-1')
            )

    # Campos para el archivo de Percepciones
    export_santafe_file_per = fields.Binary('Archivo Percepciones', compute=_compute_files_per)
    export_santafe_filename_per = fields.Char('Nombre Archivo Percepciones', compute=_compute_files_per)
        
    def compute_santafe_data(self):
        """
        Genera los archivos SIRETPER para DGR Santafe:
        PERCEPCIONES:
            - DATOSPERC.txt         → detalle de percepciones por factura
            - PERCECIONESRETPER.txt → datos de los sujetos percibidos
            - NCFACTPERC.txt        → relación NC ↔ Factura

        RETENCIONES:
            - DATOSRET.txt  → detalle de retenciones por pago/factura
            - RETPER.txt    → datos de los sujetos retenidos
        """
        self.ensure_one()
        CRLF = '\r\n'

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------
        def _tipo_doc(partner):
            nombre = (partner.l10n_latam_identification_type_id.name or '').upper()
            if 'CUIT' in nombre or 'VAT' in nombre:
                return '3'
            if 'CUIL' in nombre:
                return '2'
            return '1'

        def _campo_cuit(partner):
            """tipo_doc(1) + CUIT(11) = 12 chars"""
            return (_tipo_doc(partner) + (partner.vat or '').ljust(11))[:12]

        def _linea_retper(partner):
            """Línea de sujeto para RETPER.txt / PERCECIONESRETPER.txt"""
            cuit12 = _campo_cuit(partner)
            razon_social = (partner.name or '')[:40].ljust(40)
            domicilio = (
                ((partner.street or '') + ' ' + (partner.street2 or '')).strip()
            )[:40].ljust(40)
            cod_postal = (partner.zip or '00000')[:5].ljust(5)
            localidad = (partner.city or '')[:14].ljust(14)
            provincia = (partner.state_id.name if partner.state_id else '')[:30].ljust(30)
            cp_num = (partner.zip or '0000')[:4].zfill(4)
            return cuit12 + razon_social + domicilio + cod_postal + localidad + provincia + cp_num + CRLF

        def _split_nombre_comp(nombre):
            """Devuelve (pto_vta 4 chars, nro_comp 8 chars) desde 'FA-A 00001-00000001'"""
            partes = (nombre or '').replace(' ', '').split('-')
            if len(partes) >= 2:
                return partes[-2][-4:].zfill(4), partes[-1][-8:].zfill(8)
            return '0001', '00000001'

        # ==================================================================
        # PERCEPCIONES  (facturas de venta)
        # ==================================================================
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date asc')

        string_datosperc = ''
        string_retper_per = ''
        cuits_per = set()

        for invoice in invoices:
            groups = invoice.tax_totals.get('groups_by_subtotal', {})
            taxes = groups.get('Importe libre de impuestos') or groups.get('Base imponible') or []

            for tax in taxes:
                if tax.get('tax_group_name') != 'Perc IIBB Santafe':
                    continue

                partner = invoice.partner_id
                cuit12 = _campo_cuit(partner)
                fecha = str(invoice.invoice_date).replace('-', '')
                letra = invoice.l10n_latam_document_type_id.l10n_ar_letter or ' '
                pto_vta, nro_comp = _split_nombre_comp(invoice.name)

                # Montos (multimoneda)
                if invoice.currency_id.name != 'ARS':
                    tax_amount = 0.0
                    for ml in invoice.line_ids:
                        if ml.name == 'Percepción IIBB Santafe Aplicada':
                            tax_amount = ml.credit
                            break
                    base_amount = tax.get('tax_group_base_amount', 0.0) * invoice.l10n_ar_currency_rate
                else:
                    tax_amount = tax.get('tax_group_amount', 0.0)
                    base_amount = tax.get('tax_group_base_amount', 0.0)

                alicuota = (tax_amount * 100.0 / base_amount) if base_amount else 0.0

                # DATOSPERC.txt
                # YYYYMMDD CCCCCCCCCCCC L PPPPNNNNNNNN BBBBBBBBBBB.BB AAAAAA MMMMMMMMMM.MM
                string_datosperc += (
                    fecha + ' ' +
                    cuit12 + ' ' +
                    letra +
                    pto_vta +
                    nro_comp + ' ' +
                    ("%.2f" % base_amount).rjust(14) + ' ' +
                    ("%.3f" % alicuota).rjust(7) + ' ' +
                    ("%.2f" % tax_amount).rjust(12) +
                    CRLF
                )

                # PERCECIONESRETPER.txt — un registro por CUIT único
                cuit_key = partner.vat or ''
                if cuit_key not in cuits_per:
                    cuits_per.add(cuit_key)
                    string_retper_per += _linea_retper(partner)

        # ------------------------------------------------------------------
        # Notas de crédito → NCFACTPERC.txt
        # ------------------------------------------------------------------
        nc_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date asc')

        string_nc = ''
        for nc in nc_invoices:
            groups = nc.tax_totals.get('groups_by_subtotal', {})
            taxes = groups.get('Importe libre de impuestos') or groups.get('Base imponible') or []
            for tax in taxes:
                if tax.get('tax_group_name') != 'Perc IIBB Santafe':
                    continue

                cuit12 = _campo_cuit(nc.partner_id)
                fecha_nc = str(nc.invoice_date).replace('-', '')
                letra_nc = nc.l10n_latam_document_type_id.l10n_ar_letter or ' '
                pto_nc, nro_nc = _split_nombre_comp(nc.name)

                if nc.reversed_entry_id:
                    fac = nc.reversed_entry_id
                    fecha_fac = str(fac.invoice_date).replace('-', '')
                    letra_fac = fac.l10n_latam_document_type_id.l10n_ar_letter or ' '
                    pto_fac, nro_fac = _split_nombre_comp(fac.name)
                else:
                    fecha_fac, letra_fac, pto_fac, nro_fac = fecha_nc, letra_nc, pto_nc, nro_nc

                if nc.currency_id.name != 'ARS':
                    tax_amount_nc = tax.get('tax_group_amount', 0.0) * nc.l10n_ar_currency_rate
                else:
                    tax_amount_nc = tax.get('tax_group_amount', 0.0)

                string_nc += (
                    cuit12 + ' ' +
                    fecha_nc + ' ' +
                    letra_nc + pto_nc + nro_nc + ' ' +
                    fecha_fac + ' ' +
                    letra_fac + pto_fac + nro_fac + ' ' +
                    ("%.2f" % tax_amount_nc).rjust(12) +
                    CRLF
                )

        # ==================================================================
        # RETENCIONES (pagos + facturas de compra)
        # ==================================================================
        string_datosret = ''
        string_retper_ret = ''
        cuits_ret = set()

        # --- desde account.payment ---
        payments = self.env['account.payment'].search([
            ('payment_type', '=', 'outbound'),
            ('state', 'not in', ['cancel', 'draft']),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

        for payment in payments:
            if not payment.withholding_number:
                continue
            if not self.tax_withholding:
                continue
            if payment.tax_withholding_id.id != self.tax_withholding.id:
                continue

            partner = payment.partner_id
            cuit12 = _campo_cuit(partner)
            fecha = str(payment.date).replace('-', '')

            # Código de comprobante: 99 = Orden de Pago (valor más común para retenciones)
            cod_comp = '99'
            nro_cert = (payment.withholding_number or '').zfill(8)[-8:]
            base = float(payment.withholding_base_amount or 0.0)

            # Alícuota desde el padrón activo del partner
            alicuota_ret = partner.get_amount_alicuot_santafe('ret', payment.date)
            monto_ret = round(base * alicuota_ret / 100.0, 2)

            # DATOSRET.txt
            # YYYYMMDD CCCCCCCCCCCC TT NNNNNNNN BBBBBBBBBBB.BB AAAAAA MMMMMMMMMM.MM
            string_datosret += (
                fecha + ' ' +
                cuit12 + ' ' +
                cod_comp + ' ' +
                nro_cert + ' ' +
                ("%.2f" % base).rjust(14) + ' ' +
                ("%.3f" % alicuota_ret).rjust(7) + ' ' +
                ("%.2f" % monto_ret).rjust(12) +
                CRLF
            )

            # RETPER.txt — un registro por CUIT único
            cuit_key = partner.vat or ''
            if cuit_key not in cuits_ret:
                cuits_ret.add(cuit_key)
                string_retper_ret += _linea_retper(partner)

        # --- desde facturas de compra (si también tienen retención) ---
        in_invoices = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date asc')

        for invoice in in_invoices:
            groups = invoice.tax_totals.get('groups_by_subtotal', {})
            taxes = groups.get('Importe libre de impuestos') or groups.get('Base imponible') or []
            for tax in taxes:
                if tax.get('tax_group_name') != 'Ret IIBB Santafe':
                    continue

                partner = invoice.partner_id
                cuit12 = _campo_cuit(partner)
                fecha = str(invoice.invoice_date).replace('-', '')
                cod_comp = '01'  # Factura
                pto_vta, nro_comp = _split_nombre_comp(invoice.name)
                nro_cert = nro_comp  # en facturas usamos el nro de comprobante

                if invoice.currency_id.name != 'ARS':
                    tax_amount = tax.get('tax_group_amount', 0.0) * invoice.l10n_ar_currency_rate
                    base_amount = tax.get('tax_group_base_amount', 0.0) * invoice.l10n_ar_currency_rate
                else:
                    tax_amount = tax.get('tax_group_amount', 0.0)
                    base_amount = tax.get('tax_group_base_amount', 0.0)

                alicuota = (tax_amount * 100.0 / base_amount) if base_amount else 0.0

                string_datosret += (
                    fecha + ' ' +
                    cuit12 + ' ' +
                    cod_comp + ' ' +
                    nro_cert + ' ' +
                    ("%.2f" % base_amount).rjust(14) + ' ' +
                    ("%.3f" % alicuota).rjust(7) + ' ' +
                    ("%.2f" % tax_amount).rjust(12) +
                    CRLF
                )

                cuit_key = partner.vat or ''
                if cuit_key not in cuits_ret:
                    cuits_ret.add(cuit_key)
                    string_retper_ret += _linea_retper(partner)

        # ==================================================================
        # Guardar en campos del modelo
        # ==================================================================
        self.export_santafe_data_per = string_datosperc       # → DATOSPERC.txt
        self.export_santafe_data_nc = string_nc               # → NCFACTPERC.txt
        self.export_santafe_data = string_retper_per          # → PERCECIONESRETPER.txt
        self.export_santafe_data_ret = string_datosret        # → DATOSRET.txt
        # RETPER.txt necesita un campo nuevo (ver abajo)
        self.export_santafe_data_retper = string_retper_ret
    