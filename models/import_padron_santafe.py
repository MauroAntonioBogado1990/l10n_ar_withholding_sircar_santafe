# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime
import base64
import logging
import re
import io
import openpyxl

_logger = logging.getLogger(__name__)


class ImportPadronSantaFe(models.Model):
    _name = 'import.padron.santafe'
    _description = 'import.padron.santafe'

    def _b64_to_bytes(self, b64val):
        """Convierte un Binary de Odoo a bytes reales, tolerante a padding roto y prefijos data:."""
        if not b64val:
            return b''

        # Odoo normalmente da bytes; a veces puede venir str
        if isinstance(b64val, (bytes, bytearray)):
            b64s = b64val.decode('ascii', errors='ignore')
        else:
            b64s = str(b64val)

        b64s = b64s.strip()

        # Si viene "data:...;base64,XXXX"
        if b64s.lower().startswith('data:') and ',' in b64s:
            b64s = b64s.split(',', 1)[1]

        # eliminar espacios/saltos
        b64s = ''.join(b64s.split())

        # arreglar padding "=" faltante
        missing = (-len(b64s)) % 4
        if missing:
            b64s += '=' * missing

        try:
            return base64.b64decode(b64s)
        except Exception as e:
            _logger.error("Base64 inválido (incorrect padding). len=%s err=%s", len(b64s), e)
            raise ValidationError("El archivo subido llegó corrupto (base64 inválido). Reintente subirlo.")
    
    def btn_process_coe116(self):
        """
        1. Lee coe116_file → arma mapa CUIT → tipo (CM/CL/E)
        2. Lee padron_file  → arma mapa CUIT → (coeficiente, porcentaje)
        3. Cruza ambos mapas con santafe.padron y actualiza:
        - type_contr_insc
        - a_per (si type_alicuot=P) o a_ret (si type_alicuot=R)
            según la fórmula:
            CM → coef * 0.5 * porc
            CL → coef * porc
            E  → 0.0
        """
        self.ensure_one()

        if not self.coe116_file:
            raise ValidationError('Debe cargar el archivo COE116 (RG 116/10) para comparar.')
        if not self.padron_file:
            raise ValidationError('El archivo de padrón original (padron_file) es necesario para calcular alícuotas.')

        # ------------------------------------------------------------------
        # Helper: parsear float tolerante
        # ------------------------------------------------------------------
        def _pf(s):
            try:
                s = str(s or '').strip()
                if not s or all(c in '-.' for c in s):
                    return 0.0
                return float(s.replace(',', '.'))
            except Exception:
                return 0.0

        # ------------------------------------------------------------------
        # 1. Parsear coe116_file → {cuit: tipo}
        # ------------------------------------------------------------------
        #coe_text = self._decode_file(self.coe116_file)
        def _decode_to_text(binary_field):
            file_bytes = self._b64_to_bytes(binary_field)
            file_text = None
            for enc in ('utf-8', 'utf-8-sig', 'cp1252', 'latin-1'):
                try:
                    file_text = file_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if file_text is None:
                file_text = file_bytes.decode('latin-1', errors='replace')
            return file_text
        
        coe_text = _decode_to_text(self.coe116_file)
        cuit_tipo_map = {}

        for line in coe_text.splitlines():
            line = line.strip()
            if not line:
                continue
            partes = line.split()
            cuit_encontrado = next(
                (p for p in partes if len(''.join(filter(str.isdigit, p))) == 11), None
            )
            tipo_encontrado = next(
                (p.upper() for p in partes if p.upper() in ('CM', 'CL', 'E')), None
            )
            if cuit_encontrado and tipo_encontrado:
                cuit_limpio = ''.join(filter(str.isdigit, cuit_encontrado))
                cuit_tipo_map[cuit_limpio] = tipo_encontrado

        if not cuit_tipo_map:
            raise ValidationError("No se encontraron CUITs o Tipos válidos en el archivo COE116.")

        # ------------------------------------------------------------------
        # 2. Parsear padron_file → {cuit: (coeficiente, porcentaje)}
        #
        #    Formato de línea de datos (RG 116/10):
        #    CUIT  COEF  PERIODO  DENOMINACION...  PORCENTAJE
        #
        #    Ejemplo:
        #    30716656043     0.0109  202603  0800DONROUNCH S R L    1.5
        #
        #    - coeficiente : token[1]  (justo después del CUIT)
        #    - porcentaje  : último token numérico de la línea
        #    - Se ignoran líneas de cabecera (sin CUIT de 11 dígitos en pos 0)
        # ------------------------------------------------------------------
        #padron_text = self._decode_file(self.padron_file)
        padron_text = _decode_to_text(self.padron_file)
        cuit_valores_map = {}  # {cuit: (coef, porc)}

        for line in padron_text.splitlines():
            line_strip = line.strip()
            if not line_strip:
                continue

            partes = line_strip.split()

            # El primer token debe ser un CUIT de 11 dígitos
            primer_token = partes[0] if partes else ''
            digitos = ''.join(filter(str.isdigit, primer_token))
            if len(digitos) != 11:
                continue  # cabecera o línea que no es dato

            cuit = digitos

            # coeficiente: segundo token (puede ser '-.----' para exentos)
            coef = _pf(partes[1]) if len(partes) > 1 else 0.0

            # porcentaje: último token numérico
            # recorremos desde el final buscando el primer token convertible a float
            porc = 0.0
            for tok in reversed(partes):
                try:
                    val = float(tok.replace(',', '.'))
                    porc = val
                    break
                except ValueError:
                    continue

            cuit_valores_map[cuit] = (coef, porc)

        # ------------------------------------------------------------------
        # 3. Actualizar santafe.padron
        # ------------------------------------------------------------------
        # Solo los registros cuyos CUITs aparecen en el COE116
        padrones_a_actualizar = self.env['santafe.padron'].search([
            ('name', 'in', list(cuit_tipo_map.keys()))
        ])

        actualizados = 0
        sin_valores = []  # CUITs del COE116 que no se encontraron en padron_file

        # for padron in padrones_a_actualizar:
        #     cuit = padron.name
        #     nuevo_tipo = cuit_tipo_map.get(cuit)
        #     if not nuevo_tipo:
        #         continue

        #     # Calcular alícuota
        #     coef, porc = cuit_valores_map.get(cuit, (0.0, 0.0))

        #     if not cuit_valores_map.get(cuit):
        #         sin_valores.append(cuit)

        #     if nuevo_tipo == 'CM':
        #         alicuota = round(coef * 0.5 * porc, 4)
        #     elif nuevo_tipo == 'CL':
        #         alicuota = round(coef * porc, 4)
        #     else:  # E → Exento
        #         alicuota = 0.0

        #     # Armar el write según si es Percepción o Retención
        #     write_vals = {'type_contr_insc': nuevo_tipo}

        #     if padron.type_alicuot == 'P':
        #         write_vals['a_per'] = alicuota
        #     # elif padron.type_alicuot == 'R':
        #     #     write_vals['a_ret'] = alicuota

        #     padron.sudo().write(write_vals)
        #     actualizados += 1
        for padron in padrones_a_actualizar:
            cuit = padron.name
            nuevo_tipo = cuit_tipo_map.get(cuit)
            if not nuevo_tipo:
                continue

            valores = cuit_valores_map.get(cuit)
            if not valores:
                sin_valores.append(cuit)
                coef = 0.0
            else:
                coef = valores[0]

            # Actualizar santafe.padron
            padron.sudo().write({
                'type_contr_insc': nuevo_tipo,
                'coeficiente': coef,
            })

            # Propagar coeficiente al partner (solo al registro activo)  ← DENTRO del for
            partner = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('parent_id', '=', False)
            ], limit=1)

            if partner:
                if padron.type_alicuot == 'P':
                    linea_activa = partner.alicuot_per_santafe_ids.filtered(
                        lambda l: l.padron_activo
                    )
                    if linea_activa:
                        linea_activa[0].sudo().write({
                            'coeficiente': coef,
                            'type_contr_insc': nuevo_tipo,
                        })
                elif padron.type_alicuot == 'R':
                    linea_activa = partner.alicuot_ret_santafe_ids.filtered(
                        lambda l: l.padron_activo
                    )
                    if linea_activa:
                        linea_activa[0].sudo().write({
                            'coeficiente': coef,
                            'type_contr_insc': nuevo_tipo,
                        })

            actualizados += 1  # ← también dentro del for, al final

        # ------------------------------------------------------------------
        # 4. Resultado
        # ------------------------------------------------------------------
        advertencia = ''
        if sin_valores:
            advertencia = (
                f"\n⚠ {len(sin_valores)} CUIT(s) del COE116 no se encontraron "
                f"en padron_file (alícuota calculada como 0):\n"
                + '\n'.join(sin_valores)
            )

        self.coe116_result = (
            f"Comparación finalizada.\n"
            f"CUITs procesados del COE116: {len(cuit_tipo_map)}\n"
            f"Registros de Padrón Santa Fe actualizados: {actualizados}"
            + advertencia
        )
        self.state = 'coe_processed'
    

    def btn_process(self):
        self.ensure_one()

        if not self.padron_file:
            raise ValidationError('Debe seleccionar el archivo.')
        if self.state != 'draft':
            raise ValidationError('¡El archivo ya fue procesado!')

        def _parse_float(s):
            try:
                if not s: return 0.0
                s_raw = str(s).strip()
                if not s_raw or all(ch == '-' for ch in s_raw): return 0.0
                return float(s_raw.replace(',', '.').replace('-', ''))
            except Exception:
                return 0.0

        def _parse_compact_date(s):
            s = (s or '').strip()
            if not s: return None
            s = s.zfill(8)
            if len(s) == 8 and s.isdigit():
                return datetime.strptime(s, '%d%m%Y').date()
            return None

        def _normalize_cuit(cuit_raw):
            return ''.join(filter(str.isdigit, str(cuit_raw or '')))

        # ------------------------------------------------------------------
        # PASO 1: Decodificar y detectar formato
        # ------------------------------------------------------------------
        file_bytes = base64.b64decode(self.padron_file)
        delimiter  = (self.delimiter or ';').strip() or ';'
        is_xlsx    = file_bytes[:4] == b'PK\x03\x04'

        # ------------------------------------------------------------------
        # PASO 2: Si es XLSX → convertir a CSV temporal en disco
        #         Si es CSV  → escribir bytes a archivo temporal igual
        #         En ambos casos terminamos con un path a un CSV en /tmp
        # ------------------------------------------------------------------
        import tempfile, csv, os

        tmp_csv_path = None

        try:
            if is_xlsx:
                _logger.info("BTN_PROCESS: XLSX detectado → convirtiendo a CSV temporal...")

                tmp_fd, tmp_csv_path = tempfile.mkstemp(suffix='.csv', prefix='padron_sf_')
                os.close(tmp_fd)

                def _cell_to_str(cell):
                    """
                    Convierte celda de openpyxl a string limpio.
                    - Floats enteros (20290957371.0) → '20290957371'  (sin .0)
                    - Floats decimales (3.5)          → '3.5'          (con decimal)
                    - None                            → ''
                    - Resto                           → str()
                    """
                    if cell is None:
                        return ''
                    if isinstance(cell, float):
                        # Si es entero exacto (sin parte decimal), convertir a int primero
                        if cell == int(cell):
                            return str(int(cell))
                        else:
                            return str(cell)
                    if isinstance(cell, int):
                        return str(cell)
                    return str(cell).strip()

                try:
                    wb = openpyxl.load_workbook(
                        io.BytesIO(file_bytes),
                        read_only=True,
                        data_only=True,
                    )
                    ws = wb.active

                    filas_escritas = 0
                    with open(tmp_csv_path, 'w', encoding='utf-8', newline='') as fcsv:
                        writer = csv.writer(fcsv, delimiter=';')
                        for row in ws.iter_rows(values_only=True):
                            writer.writerow([_cell_to_str(cell) for cell in row])
                            filas_escritas += 1
                            if filas_escritas % 100_000 == 0:
                                _logger.info(
                                    "BTN_PROCESS: Conversión XLSX→CSV: %s filas escritas...",
                                    filas_escritas
                                )

                    wb.close()
                    del file_bytes
                    _logger.info("BTN_PROCESS: Conversión finalizada. Total filas: %s", filas_escritas)

                except Exception as e:
                    _logger.error("BTN_PROCESS: Error convirtiendo XLSX: %s", e)
                    raise ValidationError(f'Error al leer el archivo Excel: {e}')

            else:
                _logger.info("BTN_PROCESS: CSV/TXT detectado → escribiendo a temporal...")

                tmp_fd, tmp_csv_path = tempfile.mkstemp(suffix='.csv', prefix='padron_sf_')
                os.close(tmp_fd)

                # Detectar encoding y escribir a temporal
                file_text = None
                for enc in ('utf-8', 'utf-8-sig', 'cp1252', 'latin-1'):
                    try:
                        file_text = file_bytes.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if file_text is None:
                    file_text = file_bytes.decode('latin-1', errors='replace')

                del file_bytes  # liberar RAM

                with open(tmp_csv_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(file_text)
                del file_text

            # ------------------------------------------------------------------
            # PASO 3: Cargar CUITs de partners desde BD (1 sola query)
            # ------------------------------------------------------------------
            self.env.cr.execute(
                "SELECT id, vat FROM res_partner "
                "WHERE vat IS NOT NULL AND parent_id IS NULL"
            )
            partner_vat_map = {}
            for pid, vat in self.env.cr.fetchall():
                cuit_norm = _normalize_cuit(vat)
                if cuit_norm:
                    partner_vat_map[cuit_norm] = pid

            cuit_partners_norm = set(partner_vat_map.keys())

            if not cuit_partners_norm:
                raise ValidationError('No hay partners con CUIT cargados en el sistema.')

            # ------------------------------------------------------------------
            # PASO 4: Cargar padrón existente desde BD (1 sola query)
            # ------------------------------------------------------------------
            self.env.cr.execute(
                "SELECT id, name, type_alicuot FROM santafe_padron"
            )
            padron_map = {}
            for pid, name, type_alicuot in self.env.cr.fetchall():
                cuit_norm = _normalize_cuit(name)
                if cuit_norm and type_alicuot:
                    padron_map[(cuit_norm, type_alicuot)] = pid

            # ------------------------------------------------------------------
            # PASO 5: Leer CSV temporal línea por línea (nunca carga todo en RAM)
            # ------------------------------------------------------------------
            
            BATCH_SIZE   = 500
            PARTNER_BATCH = 1000

            to_create    = []
            to_update    = {}   # {padron_id: vals}
            padrones_ids = []   # todos los IDs tocados

            procesados = 0
            omitidos   = 0
            today      = fields.Date.today()
     
            with open(tmp_csv_path, 'r', encoding='utf-8', newline='') as fcsv:
                # ── DIAGNÓSTICO TEMPORAL ─────────────────────────
                with open(tmp_csv_path, 'r', encoding='utf-8', newline='') as fdiag:
                    reader_diag = csv.reader(fdiag, delimiter=';')
                    for i, row in enumerate(reader_diag):
                        if i >= 5:
                            break
                        _logger.info("DIAG fila %s → %s", i, row)
                sample_cuits = list(cuit_partners_norm)[:5]
                _logger.info("DIAG CUITs en BD (muestra): %s", sample_cuits)
                cuit_buscar = '20290957371'
                _logger.info("DIAG CUIT %s en BD: %s", cuit_buscar, cuit_buscar in cuit_partners_norm)
                # ── 
                reader = csv.reader(fcsv, delimiter=';')

                for lista in reader:
                    if len(lista) < 11:
                        omitidos += 1
                        continue

                    cuit = _normalize_cuit(lista[3])
                    if not cuit or cuit not in cuit_partners_norm:
                        continue

                    pub_date   = _parse_compact_date(lista[0]) or today
                    f_from     = _parse_compact_date(lista[1]) or today
                    f_to       = _parse_compact_date(lista[2]) or today
                    type_contr = (lista[4] or '').strip()
                    alta_baja  = 'S' if (lista[6] or '').strip() == 'S' else 'N'
                    a_per      = _parse_float(lista[7])
                    a_ret      = _parse_float(lista[8])
                    nro_grupo  = (lista[9] or '').strip()

                    base_vals = {
                        'name':                cuit,
                        'publication_date':    pub_date,
                        'effective_date_from': f_from,
                        'effective_date_to':   f_to,
                        'type_contr_insc':     type_contr,
                        'alta_baja':           alta_baja,
                        'cambio':              False,
                    }

                    # Percepción
                    vals_p = {**base_vals, 'type_alicuot': 'P',
                            'a_per': a_per, 'a_ret': 0.0,
                            'nro_grupo_perc': nro_grupo}
                    p_id = padron_map.get((cuit, 'P'))
                    if p_id:
                        to_update[p_id] = vals_p
                    else:
                        to_create.append(vals_p)

                    # Retención
                    vals_r = {**base_vals, 'type_alicuot': 'R',
                            'a_ret': a_ret, 'a_per': 0.0,
                            'nro_grupo_ret': nro_grupo}
                    r_id = padron_map.get((cuit, 'R'))
                    if r_id:
                        to_update[r_id] = vals_r
                    else:
                        to_create.append(vals_r)

                    procesados += 1

                    # Flush batch creates
                    if len(to_create) >= BATCH_SIZE:
                        nuevos = self.env['santafe.padron'].sudo().with_context(
                            skip_partner_update=True
                        ).create(to_create)
                        padrones_ids.extend(nuevos.ids)
                        to_create.clear()
                        self.env['santafe.padron'].invalidate_model()

            # Flush creates remanentes
            if to_create:
                nuevos = self.env['santafe.padron'].sudo().with_context(
                    skip_partner_update=True
                ).create(to_create)
                padrones_ids.extend(nuevos.ids)
                to_create.clear()

            # ------------------------------------------------------------------
            # PASO 6: Updates masivos agrupados
            # ------------------------------------------------------------------
            from collections import defaultdict
            UPDATE_BATCH = 500
            update_items = list(to_update.items())

            for i in range(0, len(update_items), UPDATE_BATCH):
                batch = update_items[i:i + UPDATE_BATCH]

                grupos = defaultdict(list)
                for pid, vals in batch:
                    key = tuple(sorted((k, str(v)) for k, v in vals.items()))
                    grupos[key].append((pid, vals))

                for key, items in grupos.items():
                    ids_batch = [item[0] for item in items]
                    vals_ref  = items[0][1]
                    self.env['santafe.padron'].sudo().with_context(
                        skip_partner_update=True
                    ).browse(ids_batch).write(vals_ref)

                padrones_ids.extend([pid for pid, _ in batch])
                self.env['santafe.padron'].invalidate_model()

            # ------------------------------------------------------------------
            # PASO 7: _update_partner_alicuotas UNA sola vez, en chunks
            # ------------------------------------------------------------------
            for i in range(0, len(padrones_ids), PARTNER_BATCH):
                chunk = self.env['santafe.padron'].sudo().browse(
                    padrones_ids[i:i + PARTNER_BATCH]
                )
                chunk._update_partner_alicuotas(chunk)
                self.env['res.partner'].invalidate_model()

            _logger.info(
                "BTN_PROCESS finalizado: procesados=%s omitidos=%s",
                procesados, omitidos
            )

        finally:
            # ------------------------------------------------------------------
            # PASO 8: Limpiar archivo temporal SIEMPRE, incluso si hay error
            # ------------------------------------------------------------------
            if tmp_csv_path and os.path.exists(tmp_csv_path):
                try:
                    os.remove(tmp_csv_path)
                    _logger.info("BTN_PROCESS: Archivo temporal eliminado: %s", tmp_csv_path)
                except Exception as e:
                    _logger.warning("BTN_PROCESS: No se pudo eliminar temporal: %s", e)

        self.state = 'processed'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Proceso completado',
                'message': (
                    f'Se procesaron {procesados} clientes exitosamente.\n'
                    f'Formato: {"Excel (.xlsx)" if is_xlsx else "CSV/TXT"}'
                ),
                'type': 'success',
                'sticky': False,
            }
        }





    @api.depends('padron_file')
    def compute_lineas_archivo(self):
        for rec in self:
            rec.lineas_archivo = 0
            rec.file_content_tmp = ''
            if not rec.padron_file:
                continue

            try:
                file_bytes = rec._b64_to_bytes(rec.padron_file)

                # Detectar XLSX por firma de bytes
                if file_bytes[:4] == b'PK\x03\x04':
                    # Para XLSX solo contamos filas sin cargar todo en RAM
                    try:
                        wb = openpyxl.load_workbook(
                            io.BytesIO(file_bytes),
                            read_only=True,
                            data_only=True
                        )
                        ws = wb.active
                        # max_row puede ser None en algunos XLSX, contamos manualmente
                        count = ws.max_row or sum(1 for _ in ws.iter_rows())
                        wb.close()
                        rec.lineas_archivo = count
                        rec.file_content_tmp = f'[Archivo Excel - {count} filas]'
                    except Exception as e:
                        _logger.error("Error leyendo XLSX en compute: %s", e)
                        rec.lineas_archivo = 0
                        rec.file_content_tmp = '[Error leyendo Excel]'
                else:
                    # CSV/TXT — flujo original
                    file_text = None
                    for enc in ('utf-8', 'utf-8-sig', 'cp1252', 'latin-1'):
                        try:
                            file_text = file_bytes.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    if file_text is None:
                        file_text = file_bytes.decode('latin-1', errors='replace')

                    rec.file_content_tmp = file_text
                    rec.lineas_archivo = len(file_text.splitlines())

            except Exception as e:
                _logger.error("Error decodificando archivo: %s", e)
                rec.lineas_archivo = 0
                rec.file_content_tmp = ''
    
    name = fields.Char('Nombre')
    padron_file = fields.Binary('Archivo')
    delimiter = fields.Char('Delimitador', default=";")
    #state = fields.Selection(selection=[('draft', 'Borrador'), ('processed', 'Procesado')],string='Estado',default='draft')
    ##agregado tres campos
    coe116_file = fields.Binary('Archivo COE116')
    coe116_result = fields.Text('Resultado COE116')
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'), 
            ('processed', 'Procesado'),
            ('coe_processed', 'COE Finalizado')
        ],
        string='Estado',
        default='draft'
    )
    #hasta aqui
    file_content = fields.Text('Texto archivo')
    file_content_tmp = fields.Text('Texto archivo')
    not_processed_content = fields.Text('Texto no procesado')
    clientes_cargados = fields.Text('Clientes cargados')
    skip_first_line = fields.Boolean('Saltear primera linea', default=True)
    padron_match = fields.Selection(selection=[('cuit', 'CUIT')], string='Buscar clientes por...', default='cuit')
    lineas_archivo = fields.Integer(compute=compute_lineas_archivo, store=True)