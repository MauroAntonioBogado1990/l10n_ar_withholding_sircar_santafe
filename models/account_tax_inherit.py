# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AccountTax(models.Model):
    """
    Extensión del modelo de Impuestos (account.tax).
    Añadimos una marca para identificar específicamente el impuesto de Santa Fe.
    """
    _inherit = "account.tax"

    # Campo: Impuesto de Retención Santa Fe
    # Es una casilla de verificación (Booleano). 
    # Si está marcada, el sistema sabe que este impuesto debe seguir las reglas de Santa Fe.
    tax_santafe_ret = fields.Boolean('Imp. Ret Santa Fe', default=False)

    def create_payment_withholdings(self, payment_group):
        """
        Esta función controla la creación automática de certificados de retención 
        durante un pago.
        """
        for rec in self:
            # Si el impuesto tiene marcada la casilla 'tax_santafe_ret' (es de Santa Fe):
            if rec.tax_santafe_ret:
                # DETENEMOS el proceso estándar aquí (return).
                # Hacemos esto porque el cálculo de Santa Fe se hace de forma manual/especial
                # en el modelo de 'payment_group' que vimos anteriormente. 
                # Así evitamos que Odoo cree una retención duplicada o con valores genéricos.
                return
            else:
                # Si NO es un impuesto de Santa Fe, dejamos que Odoo siga su camino normal
                # y ejecute las funciones estándar de otros impuestos.
                return super(AccountTax, rec).create_payment_withholdings(payment_group)