import calendar
from decimal import Decimal

from django import forms
from django.conf import settings
from django.forms import formset_factory
from django.forms import inlineformset_factory
from django.utils import timezone

from inventario.models import Categoria, TipoOro

from .models import ArticuloEmpeno, Cliente, Contrato


def _sumar_meses(fecha, meses):
    mes_indice = fecha.month - 1 + meses
    anio = fecha.year + mes_indice // 12
    mes = mes_indice % 12 + 1
    return fecha.replace(
        year=anio,
        month=mes,
        day=min(fecha.day, calendar.monthrange(anio, mes)[1]),
    )


class CamposBootstrapMixin:
    def aplicar_estilos(self):
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"


class ClienteForm(CamposBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ("documento", "nombres", "telefono", "direccion")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class ContratoCrearForm(CamposBootstrapMixin, forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.order_by("nombres"),
        required=False,
        label="Cliente existente",
        help_text="Selecciona un cliente o completa los datos para registrar uno nuevo.",
    )
    documento = forms.CharField(max_length=30, required=False, label="Documento")
    nombres = forms.CharField(max_length=150, required=False, label="Nombres")
    telefono = forms.CharField(max_length=30, required=False, label="Teléfono")
    direccion = forms.CharField(max_length=200, required=False, label="Dirección")
    fecha_inicio = forms.DateField(
        label="Fecha de inicio",
        help_text="Se asigna automáticamente a la fecha actual.",
        initial=timezone.localdate,
        disabled=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_vencimiento = forms.DateField(
        label="Fecha de vencimiento",
        help_text="Se calcula automáticamente a cuatro meses.",
        disabled=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valor_prestamo = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Valor del préstamo",
    )
    observaciones = forms.CharField(
        required=False, label="Observaciones", widget=forms.Textarea(attrs={"rows": 3})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inicio = timezone.localdate()
        self.fields["fecha_inicio"].initial = inicio
        self.fields["fecha_vencimiento"].initial = _sumar_meses(
            inicio, settings.PLAZO_CONTRATO_MESES
        )
        self.aplicar_estilos()
        self.fields["cliente"].widget.attrs["class"] = "form-select"

    def clean(self):
        datos = super().clean()
        cliente = datos.get("cliente")
        documento = datos.get("documento")
        if not cliente:
            cliente_existente = Cliente.objects.filter(documento=documento).first() if documento else None
            if cliente_existente is None:
                for campo in ("documento", "nombres", "telefono"):
                    if not datos.get(campo):
                        self.add_error(campo, "Completa este dato para registrar el cliente.")
        if (
            datos.get("fecha_inicio")
            and datos.get("fecha_vencimiento")
        ):
            fecha_esperada = _sumar_meses(
                datos["fecha_inicio"], settings.PLAZO_CONTRATO_MESES
            )
            if datos["fecha_vencimiento"] != fecha_esperada:
                self.add_error(
                    "fecha_vencimiento",
                    "Debe corresponder al plazo estándar de cuatro meses.",
                )
        return datos

    def obtener_cliente(self):
        cliente = self.cleaned_data.get("cliente")
        if cliente:
            return cliente
        existente = Cliente.objects.filter(
            documento=self.cleaned_data["documento"]
        ).first()
        if existente:
            return existente
        return Cliente.objects.create(
            documento=self.cleaned_data["documento"],
            nombres=self.cleaned_data["nombres"],
            telefono=self.cleaned_data["telefono"],
            direccion=self.cleaned_data.get("direccion", ""),
        )


class ArticuloEmpenoForm(CamposBootstrapMixin, forms.ModelForm):
    class Meta:
        model = ArticuloEmpeno
        fields = ("categoria", "tipo_oro", "peso_gramos", "descripcion")
        widgets = {
            "descripcion": forms.TextInput(attrs={"placeholder": "Detalles opcionales"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
        self.fields["tipo_oro"].queryset = TipoOro.objects.order_by("nombre")


ArticuloEmpenoFormSet = inlineformset_factory(
    Contrato,
    ArticuloEmpeno,
    form=ArticuloEmpenoForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class PagoForm(CamposBootstrapMixin, forms.Form):
    tipo = forms.ChoiceField(
        choices=(
            ("ABONO", "Abono"),
            ("RENOVACION", "Renovación"),
            ("RETIRO", "Retiro"),
        ),
        label="Tipo de pago",
    )
    monto = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Monto recibido",
    )
    observaciones = forms.CharField(
        required=False,
        label="Observaciones",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class SimuladorEmpenoForm(CamposBootstrapMixin, forms.Form):
    valor_prestamo = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("50000"),
        label="¿Cuánto dinero necesitas?",
        help_text="Puedes solicitar hasta el máximo calculado para tus prendas.",
        error_messages={
            "min_value": "El préstamo mínimo permitido es de $ 50.000.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class SimuladorArticuloForm(CamposBootstrapMixin, forms.Form):
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.order_by("nombre"),
        label="Tipo de prenda",
    )
    tipo_oro = forms.ModelChoiceField(
        queryset=TipoOro.objects.order_by("nombre"),
        label="Tipo de oro",
    )
    peso_gramos = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Peso (gramos)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


SimuladorArticuloFormSet = formset_factory(
    SimuladorArticuloForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=5,
    validate_max=True,
)


class AnularContratoForm(CamposBootstrapMixin, forms.Form):
    observacion = forms.CharField(
        label="Motivo de anulación",
        min_length=1,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean_observacion(self):
        observacion = self.cleaned_data["observacion"].strip()
        if not observacion:
            raise forms.ValidationError("La observación de anulación es obligatoria.")
        return observacion


class PrecioLiquidacionForm(CamposBootstrapMixin, forms.Form):
    articulo_id = forms.IntegerField(widget=forms.HiddenInput)
    categoria = forms.CharField(label="Artículo", disabled=True, required=False)
    precio_venta = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Precio de venta inicial",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


PrecioLiquidacionFormSet = formset_factory(
    PrecioLiquidacionForm,
    extra=0,
)
