# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class ResCompany(models.Model):
    _inherit = "res.company"

    tax_per_santafe = fields.Many2one(
        'account.tax',
        'Impuesto de Percepción Santa Fe',
        domain=[('type_tax_use', '=', 'sale'),('tax_group_id.l10n_ar_tribute_afip_code','=','07')], 
        company_dependent=True
    )

    #esto se agrega para poder tener el porcentaje
    # Porcentaje general para Santa Fe (ejemplo: 2.50)
    l10n_ar_santafe_porcentaje_general = fields.Float(
        string='Porcentaje General Santa Fe', 
        digits=(16, 2),
        default=0.0,
        help="Alícuota a aplicar si el partner no está en el padrón.",
        company_dependent=True
    )
    #aqui habrá que ver como seran los valores de seleccion de tucuman
    regimen_santafe_ret = fields.Selection([
        ('1','1 - COMPAÑIAS DE SEGUROS'),
        ('2','2 - ORD. 40434 PROVEEDORES GCBA – RESOLUCIÓN Nº 200/AGIP/2002'),
        ('3','3 - OBRAS Y SERVICIOS SOCIALES, MUTUALES Y MEDICINA PREPAGA'),
        ('4','4 - TARJETAS CRÉDITO, COMPRA, DÉBITO Y SIMILARES'),
        ('5','5 - SERVICIOS DE TICKETS, VALES ALIMENTOS (Vigente hasta el 31/12/2019)'),
        ('6','6 - MARTILLEROS Y DEMÁS INTERMEDIARIOS'),
        ('7','7 - COMISIONISTAS, REPRESENTANTES, CONSIGNATARIOS O CUALQUIER OTRO INTERMEDIARIO PERSONA O ENTIDAD'),
        ('8','8 - REGIMEN GENERAL - (Vigente hasta el 31/10/2016 - Aplicable solo para DDJJ Originales y Rectificativas Períodos: 10-2016 y anteriores)'),
        ('16','16 - PADRÓN DE RIESGO FISCAL - (Vigente hasta el 31/12/2019)'),
        ('18','18 - RÉGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('19','19 - RETENCIÓN PARCIAL - REGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('20','20 - IMPOSIBILIDAD DE RETENER - REGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('25','25 - CONTRATACIÓN DE SERVICIOS  SUSCRIPCIÓN ON-LINE, PELÍCULAS, TV Y OTROS - (RES. 593/AGIP/2014, y Modif.) - (Régimen suspendido por Resolución Nº 26-AGIP/2015).'),
        ('26','26 - ACTIVIDADES CULTURALES Y ARTISTAS - EXTRANJEROS (Res. 594/AGIP/2014, y Modif.) - (Régimen suspendido por Resolución Nº 624-AGIP/2014)'),
        ('28','28 - PADRÓN DE ALICUOTAS DIFERENCIALES - REGÍMENES  PARTICULARES '),
        ('29','29 - PADRÓN DE REGÍMENES GENERALES'),
        ('31','31 - SERVICIOS DE GESTIÓN Y/O PROCESAMIENTO DE PAGOS PLATAFORMAS Y APLICACIONES INFORMÁTICAS - (Vigente desde 01/02/2020)'),
    ],'Regimen Retenciones AGIP', company_dependent=True)
    
    #aqui habrá que ver como seran los valores de seleccion de tucuman
    regimen_santafe_per = fields.Selection([
        ('10', '10 - PRODUCTORES DE COMBUSTIBLES LÍQUIDOS, GAS NATURAL Y COMERCIALIZADORES MAYORISTAS'),
        ('11', '11 - VENTAS DE PRODUCTOS DERIVADOS DEL PETRÓLEO (ACEITES, LUBRICANTES, ETC)'),
        ('12', '12 - PRODUCCIÓN ELABORACIÓN Y FABRICACIÓN DE PRODUCTOS COMESTIBLES Y BEBIDAS'),
        ('14', '14 - RÉGIMEN GENERAL - (Vigente hasta el 31/10/2016) - (Aplicable solo para DDJJ Originales y Rectificativas  Períodos: 10-2016  y anteriores)'),
        ('15', '15 - TERMINALES AUTOMOTRICES Y MOTOCICLETAS'),
        ('16', '16 - PADRÓN DE RIESGO FISCAL  - (Vigente hasta el 31/12/2019)'),
        ('17', '17 - CANONES Y ALQUILERES SHOPPING - (Vigente hasta el 31/12/2019)'),
        ('18', '18 - RÉGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('19', '19 - PERCEPCIÓN PARCIAL - RÉGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('20', '20 - IMPOSIBILIDAD DE PERCEPCIÓN - RÉGIMEN SIMPLIFICADO - MAGNITUDES SUPERADAS - (Vigente hasta el 31/12/2019)'),
        ('21', '21 - CONTRATOS DE FRANQUICIAS - (Vigente hasta el 31/12/2019)'),
        ('22', '22 - VENTA  AL CONTADO Y EFECTIVO - IMPORTE SUPERIOR A $ 1.000,00'),
        ('23', '23 - PORTALES DE SUBASTAS ON-LINE - CON INSCRIPTOS  EN ISIB'),
        ('24', '24 - PORTALES DE SUBASTAS ON-LINE  CON NO INSCRIPTOS EN ISIB'),
        ('27', '27 - FABRICANTES Y MAYORISTAS DE TABACO Y AFINES'),
        ('28', '28 - PADRÓN DE ALICUOTAS DIFERENCIALES - REGÍMENES PARTICULARES'),
        ('29', '29 - PADRÓN DE REGÍMENES GENERALES'),
        ('30', '30 - VENTA DIRECTA - (Vigente a partir del 01/01/2020)'),
    ],'Regimen Percepciones AGIP', company_dependent=True)
    
    l10n_ar_santafe_minimo_retencion = fields.Float(
        string='Mínimo Retención IIBB Santa Fe', 
        default=650000.0,
        help="Monto neto a partir del cual se empieza a retener."
    )
    l10n_ar_santafe_minimo_percepcion = fields.Float(
        string='Mínimo Percepción IIBB Santa Fe', 
        default=360000.0,
        help="Monto neto a partir del cual se empieza a percibir."
    )
    # Porcentaje general para cálculos de Convenio Multilateral
    l10n_ar_santafe_porcentaje_general = fields.Float(
        string='Alícuota General Santa Fe (%)', 
        default=3.5
    )