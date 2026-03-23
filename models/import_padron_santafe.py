# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime
import base64
import logging
import re

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
        _procesados = ""
        _noprocesados = ""
        vals = {}
        self.ensure_one()

        if not self.padron_match:
            raise ValidationError('Debe seleccionar metodo de busqueda de Clientes')
        if not self.delimiter:
            raise ValidationError('Debe ingresar el delimitador')
        if not self.padron_file:
            raise ValidationError('Debe seleccionar el archivo')
        if self.state != 'draft':
            raise ValidationError('Archivo procesado!')

        # -------------------------
        # Helpers
        # -------------------------
        def _parse_float(s):
            try:
                if s is None:
                    return 0.0
                s_raw = str(s).strip()
                if not s_raw:
                    return 0.0
                # si era '-----' o similar
                if all(ch == '-' for ch in s_raw):
                    return 0.0
                s2 = s_raw.replace(',', '.').replace('-', '')
                return float(s2) if s2 else 0.0
            except Exception:
                return 0.0

        def _normalize_type(tc):
            if not tc:
                return ''
            t = str(tc).strip()
            if 'E' in t:
                return 'E'
            if 'CM' in t:
                return 'CM'
            if 'CL' in t:
                return 'CL'
            return t

        def _parse_date_token(tok: str):
            """Soporta DD/MM/YYYY, DD-MM-YYYY, YYYYMMDD y DDMMYYYY."""
            if not tok:
                return None
            t = tok.strip()

            m = re.match(r'^(\d{2})[/-](\d{2})[/-](\d{4})$', t)
            if m:
                d, mo, y = m.groups()
                return datetime(int(y), int(mo), int(d))

            if re.match(r'^\d{8}$', t):
                if t.startswith(('19', '20')):
                    return datetime.strptime(t, '%Y%m%d')  # YYYYMMDD
                return datetime.strptime(t, '%d%m%Y')      # DDMMYYYY

            return None

        def _extract_dates_from_line(line: str):
            """
            Devuelve (desde, hasta).
            - Si hay 2+ fechas: toma las primeras 2.
            - Si hay 1 fecha: usa la misma para desde/hasta.
            - Si no hay: (None, None)
            """
            tokens = re.findall(r'\d{2}[/-]\d{2}[/-]\d{4}|\b\d{8}\b', line or '')
            dates = []
            for tok in tokens:
                d = _parse_date_token(tok)
                if d:
                    dates.append(d)
            if len(dates) >= 2:
                return dates[0], dates[1]
            if len(dates) == 1:
                return dates[0], dates[0]
            return None, None

        def _extract_periodo_yyyymm(line: str):
            """
            Busca un token de 6 dígitos con formato YYYYMM (ej: 202603)
            y devuelve (primer_dia_mes, ultimo_dia_mes).
            Útil para archivos RG 116/10 que traen período en vez de fechas.
            """
            import calendar
            tokens = re.findall(r'\b(\d{6})\b', line or '')
            for tok in tokens:
                y = int(tok[:4])
                m = int(tok[4:6])
                if 2000 <= y <= 2099 and 1 <= m <= 12:
                    ultimo_dia = calendar.monthrange(y, m)[1]
                    return datetime(y, m, 1), datetime(y, m, ultimo_dia)
            return None, None

        def _parse_ddmmyyyy_compacto(s: str):
            """Para el CSV largo que viene como DDMMYYYY."""
            s = (s or '').strip()
            if len(s) != 8 or not s.isdigit():
                return None
            return datetime.strptime(s[:2] + '/' + s[2:4] + '/' + s[4:], '%d/%m/%Y')

        # -------------------------
        # Decode archivo (bytes -> str)
        # -------------------------
        file_bytes = self._b64_to_bytes(self.padron_file)
        file_text = None
        for enc in ('utf-8', 'utf-8-sig', 'cp1252', 'latin-1'):
            try:
                file_text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if file_text is None:
            file_text = file_bytes.decode('latin-1', errors='replace')

        self.file_content = file_text
        lines = file_text.splitlines()  # maneja \n y \r\n

        # -------------------------
        # CAMBIO: Detectar tipo de padrón por contenido del archivo
        # RG 116/10 = Percepción ('P'), RG 176/10 = Retención ('R')
        # Se revisan las primeras 5 líneas del archivo buscando la RG.
        # Si no se detecta, tipo_padron_archivo queda en None y se
        # mantiene el comportamiento anterior (crea P y R).
        # -------------------------
        tipo_padron_archivo = None
        for header_line in lines[:5]:
            if 'RG 116' in header_line:
                tipo_padron_archivo = 'P'
                _logger.info("Archivo detectado como PERCEPCIÓN (RG 116/10)")
                break
            elif 'RG 176' in header_line:
                tipo_padron_archivo = 'R'
                _logger.info("Archivo detectado como RETENCIÓN (RG 176/10)")
                break

        # -------------------------
        # Cache CUITs
        # -------------------------
        partners = self.env['res.partner'].search([('vat', '!=', False), ('parent_id', '=', False)])
        cuit_partners = set(p.vat for p in partners if p.vat)

        # -------------------------
        # Procesar
        # -------------------------
        for i, line in enumerate(lines):
            if self.skip_first_line and i == 0:
                continue

            line = (line or '').strip()
            if not line:
                continue

            lista = line.split(self.delimiter)

            # -------- CSV largo (12+ cols) --------
            if len(lista) > 11:
                cuit = (lista[3] or '').strip()
                if not cuit or cuit not in cuit_partners:
                    continue

                publication_date = (lista[0] or '').strip()
                effective_date_from = (lista[1] or '').strip()
                effective_date_to = (lista[2] or '').strip()

                vals.clear()
                pub = _parse_ddmmyyyy_compacto(publication_date)
                f_from = _parse_ddmmyyyy_compacto(effective_date_from)
                f_to = _parse_ddmmyyyy_compacto(effective_date_to)

                # fallback por si viniera distinto
                if not f_from or not f_to:
                    f_from2, f_to2 = _extract_dates_from_line(line)
                    f_from = f_from or f_from2
                    f_to = f_to or f_to2

                vals['publication_date'] = pub or datetime.today()
                vals['effective_date_from'] = f_from or datetime.today()
                vals['effective_date_to'] = f_to or datetime.today()
                vals['name'] = cuit
                vals['type_contr_insc'] = _normalize_type(lista[4])
                vals['alta_baja'] = (lista[5] or '').strip()
                vals['a_per'] = _parse_float(lista[7])
                vals['a_ret'] = _parse_float(lista[8])
                vals['cambio'] = (lista[6] or '').strip()

                nro_grupo_perc = (lista[9] or '').strip()
                nro_grupo_ret = (lista[10] or '').strip()

                # Percepción
                padron_p = self.env['santafe.padron'].search([('name', '=', cuit), ('type_alicuot', '=', 'P')], limit=1)
                if padron_p:
                    padron_p.sudo().write({
                        'a_per': vals['a_per'],
                        'a_ret': 0.00,
                        'publication_date': vals['publication_date'],
                        'effective_date_from': vals['effective_date_from'],
                        'effective_date_to': vals['effective_date_to'],
                        'alta_baja': vals['alta_baja'],
                        'type_contr_insc': vals['type_contr_insc'],
                    })
                else:
                    create_vals = dict(vals)
                    create_vals.update({
                        'type_alicuot': 'P',
                        'a_ret': 0.0,
                        'nro_grupo_perc': nro_grupo_perc,
                    })
                    self.env['santafe.padron'].sudo().create(create_vals)

                # Retención
                padron_r = self.env['santafe.padron'].search([('name', '=', cuit), ('type_alicuot', '=', 'R')], limit=1)
                if padron_r:
                    padron_r.sudo().write({
                        'a_per': 0.00,
                        'a_ret': vals['a_ret'],
                        'publication_date': vals['publication_date'],
                        'effective_date_from': vals['effective_date_from'],
                        'effective_date_to': vals['effective_date_to'],
                        'alta_baja': vals['alta_baja'],
                        'type_contr_insc': vals['type_contr_insc'],
                    })
                else:
                    create_vals = dict(vals)
                    create_vals.update({
                        'type_alicuot': 'R',
                        'a_per': 0.0,
                        'nro_grupo_ret': nro_grupo_ret,
                    })
                    self.env['santafe.padron'].sudo().create(create_vals)

                _procesados += f"{cuit}\n"
                continue

            # -------- Caso “2 columnas” (formato variable) --------
            if len(lista) == 2:
                left = (lista[0] or '').strip()
                right = (lista[1] or '').strip()
                partes_left = left.split()

                def _is_cuit(s):
                    ds = ''.join(ch for ch in (s or '') if ch.isdigit())
                    return len(ds) == 11

                cuit = None
                denominacion = ''
                type_contr = ''

                if partes_left and _is_cuit(partes_left[0]):
                    cuit = ''.join(ch for ch in partes_left[0] if ch.isdigit())
                    if len(partes_left) >= 2:
                        type_contr = _normalize_type(partes_left[1])
                    denom_left = ' '.join(partes_left[2:]).strip() if len(partes_left) > 2 else ''
                    denominacion = (denom_left + ' ' + right).strip() if denom_left else right
                else:
                    ambas = (left + ' ' + right).split()
                    if ambas and _is_cuit(ambas[0]):
                        cuit = ''.join(ch for ch in ambas[0] if ch.isdigit())
                        denominacion = ' '.join(ambas[1:]).strip()

                if not cuit:
                    _noprocesados += f"{line}\n"
                    continue
                if cuit not in cuit_partners:
                    continue

                # ✅ fechas por regex (sin depender de índices)
                f_desde, f_hasta = _extract_dates_from_line(line)
                if not f_desde or not f_hasta:
                    _logger.warning("No se detectaron fechas (len=2) en línea %s: %r", i + 1, line)
                    f_desde = datetime.today()
                    f_hasta = datetime.today()

                vals.clear()
                vals['name'] = cuit
                vals['publication_date'] = datetime.today()
                vals['effective_date_from'] = f_desde
                vals['effective_date_to'] = f_hasta
                vals['type_contr_insc'] = type_contr if type_contr else 'CM'
                vals['alta_baja'] = 'S'
                vals['a_per'] = 0.0
                vals['a_ret'] = 0.0
                vals['cambio'] = ''

                padron_existe = self.env['santafe.padron'].search([('name', '=', cuit)], limit=1)
                if padron_existe:
                    padron_existe.sudo().write(vals)
                else:
                    create_vals = dict(vals)
                    # CAMBIO: usar tipo detectado del archivo, o 'P' como fallback
                    create_vals['type_alicuot'] = tipo_padron_archivo or 'P'
                    self.env['santafe.padron'].sudo().create(create_vals)

                _procesados += f"{cuit} {denominacion}\n"
                continue

            # -------- Caso “1 columna” (tokens variables) --------
            if len(lista) == 1:
                partes = line.split()
                if len(partes) < 2:
                    continue

                cuit = (partes[0] or '').strip()
                if cuit not in cuit_partners:
                    continue

                es_exento = False
                type_contr_insc = 'CM'  # fallback si no se encuentra nada
                idx = 1
                if len(partes) > idx and partes[idx] == 'E':
                    es_exento = True
                    idx += 1
                if len(partes) > idx and partes[idx] in ('CM', 'CL'):
                    type_contr_insc = partes[idx]

                # Fechas según tipo de padrón detectado:
                # RG 176/10 (Retención): tiene DESDE y HASTA en formato YYYYMMDD
                # RG 116/10 (Percepción): tiene período YYYYMM (derivar primer y último día del mes)
                f_desde, f_hasta = None, None
                if tipo_padron_archivo == 'R':
                    # RG 176/10: buscar fechas de 8 dígitos YYYYMMDD
                    f_desde, f_hasta = _extract_dates_from_line(line)
                elif tipo_padron_archivo == 'P':
                    # RG 116/10: buscar período YYYYMM
                    f_desde, f_hasta = _extract_periodo_yyyymm(line)
                else:
                    # No se detectó tipo: intentar ambos
                    f_desde, f_hasta = _extract_dates_from_line(line)
                    if not f_desde or not f_hasta:
                        f_desde, f_hasta = _extract_periodo_yyyymm(line)
                if not f_desde or not f_hasta:
                    _logger.warning("No se detectaron fechas (len=1) en línea %s: %r", i + 1, line)
                    f_desde = datetime.today()
                    f_hasta = datetime.today()

                # porcentaje: tomo el último token “parecido” a número
                alicuota = _parse_float(partes[-1])

                # CAMBIO: Si se detectó el tipo desde el header del archivo,
                # usar solo ese tipo. Si no se detectó (tipo_padron_archivo es None),
                # mantener comportamiento anterior creando tanto P como R.
                tipos_a_procesar = [tipo_padron_archivo] if tipo_padron_archivo else ['P', 'R']

                for tipo_a in tipos_a_procesar:
                    vals_padron = {
                        'name': cuit,
                        'publication_date': datetime.today(),
                        'effective_date_from': f_desde,
                        'effective_date_to': f_hasta,
                        'type_contr_insc': type_contr_insc,
                        'alta_baja': 'S',
                        'type_alicuot': tipo_a,
                        'a_per': alicuota if tipo_a == 'P' else 0.0,
                        'a_ret': alicuota if tipo_a == 'R' else 0.0,
                        'cambio': ''
                    }
                    pad = self.env['santafe.padron'].search([
                        ('name', '=', cuit),
                        ('type_alicuot', '=', tipo_a)
                    ], limit=1)
                    if pad:
                        pad.sudo().write(vals_padron)
                    else:
                        self.env['santafe.padron'].sudo().create(vals_padron)

                tipo_label = tipo_padron_archivo or 'P+R'
                _procesados += f"{cuit} ({tipo_label}: {alicuota}%)\n"
                continue

            # -------- fallback --------
            _noprocesados += f"{line}\n"

        self.clientes_cargados = _procesados
        self.not_processed_content = _noprocesados
        self.state = 'processed'

    @api.depends('padron_file')
    def compute_lineas_archivo(self):
        for rec in self:
            rec.lineas_archivo = 0
            rec.file_content_tmp = ''
            if not rec.padron_file:
                continue

            try:
                file_bytes = self._b64_to_bytes(rec.padron_file)
                # acá decodificás texto igual que ya venías haciendo
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