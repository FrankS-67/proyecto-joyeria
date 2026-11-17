from django import forms
from django.core.exceptions import ValidationError

from .models import (
    TIPOS_ORO_VENDIBLES,
    Prenda,
    TipoOro,
)

MAXIMO_FOTO_BYTES = 5 * 1024 * 1024


class CamposBootstrapMixin:
    def aplicar_estilos(self):
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"


class PrendaForm(CamposBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Prenda
        fields = (
            "categoria",
            "tipo_oro",
            "peso_gramos",
            "descripcion",
            "foto",
            "estado",
            "origen",
            "articulo_origen",
        )
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipos_oro = TipoOro.objects.filter(
            nombre__in=TIPOS_ORO_VENDIBLES
        ).order_by("nombre")
        if self.instance.pk and self.instance.tipo_oro_id:
            tipos_oro = (
                tipos_oro
                | TipoOro.objects.filter(pk=self.instance.tipo_oro_id)
            ).distinct()
        self.fields["tipo_oro"].queryset = tipos_oro
        self.aplicar_estilos()

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and foto.size > MAXIMO_FOTO_BYTES:
            raise ValidationError("La foto no puede superar 5 MB.")
        return foto
