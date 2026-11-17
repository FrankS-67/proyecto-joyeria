from decimal import Decimal

from django import forms
from django.forms import formset_factory

from empenos.models import Cliente
from inventario.models import (
    TIPOS_ORO_VENDIBLES,
    Prenda,
)


class PrecioCOPField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "decimal",
                    "placeholder": "Ej. 300.000",
                }
            ),
        )
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            valor = value.strip().replace("$", "").replace(" ", "")
            if "," in valor:
                entero, separador, decimales = valor.partition(",")
                if separador and "." in entero:
                    grupos = entero.split(".")
                    if len(grupos[0]) <= 3 and all(
                        len(grupo) == 3 for grupo in grupos[1:]
                    ):
                        entero = "".join(grupos)
                valor = f"{entero}.{decimales}"
            elif "." in valor:
                grupos = valor.split(".")
                if len(grupos) > 1 and len(grupos[0]) <= 3 and all(
                    len(grupo) == 3 for grupo in grupos[1:]
                ):
                    valor = "".join(grupos)
            value = valor
        return super().to_python(value)


class CamposBootstrapMixin:
    def aplicar_estilos(self):
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"


class VentaForm(CamposBootstrapMixin, forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.order_by("nombres"),
        required=False,
        label="Cliente (opcional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class DetalleVentaForm(CamposBootstrapMixin, forms.Form):
    prenda = forms.ModelChoiceField(
        queryset=Prenda.objects.none(),
        label="Prenda disponible",
    )
    precio_final = PrecioCOPField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Precio final",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prenda"].queryset = Prenda.objects.filter(
            estado=Prenda.Estado.DISPONIBLE,
            tipo_oro__nombre__in=TIPOS_ORO_VENDIBLES,
        ).select_related("categoria", "tipo_oro").order_by("categoria__nombre", "pk")
        self.fields["prenda"].label_from_instance = (
            lambda prenda: (
                f"{prenda.categoria} — {prenda.descripcion_catalogo} "
                f"(precio sugerido {prenda.precio_venta})"
            )
        )
        self.aplicar_estilos()


DetalleVentaFormSet = formset_factory(
    DetalleVentaForm,
    extra=1,
    min_num=1,
    validate_min=True,
)
