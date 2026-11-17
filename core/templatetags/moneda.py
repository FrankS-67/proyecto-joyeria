from decimal import Decimal, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def moneda(valor):
    cantidad = Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    entero = f"{int(cantidad):,}".replace(",", ".")
    return f"$ {entero}"
