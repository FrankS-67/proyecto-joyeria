from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from empenos.models import Cliente


ERROR_DATOS_CLIENTE = (
    "No fue posible validar los datos. Verifica que el documento y el teléfono "
    "coincidan con los registrados por el empleado y que el cliente aún no tenga cuenta."
)


class RegistroClienteForm(forms.Form):
    documento = forms.CharField(
        max_length=30,
        label="Documento (será tu usuario)",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "username"}),
    )
    telefono = forms.CharField(
        max_length=30,
        label="Teléfono registrado",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
    )
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )

    def clean(self):
        datos = super().clean()
        documento = datos.get("documento")
        telefono = datos.get("telefono")
        password1 = datos.get("password1")
        password2 = datos.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if password1 and documento:
            try:
                validate_password(password1, user=get_user_model()(username=documento))
            except ValidationError as error:
                self.add_error("password1", error)

        if documento and telefono:
            cliente = Cliente.objects.filter(
                documento=documento,
                telefono=telefono,
                usuario__isnull=True,
            ).first()
            User = get_user_model()
            if cliente is None or User.objects.filter(username=documento).exists():
                raise ValidationError(ERROR_DATOS_CLIENTE)
            self.cliente_id = cliente.pk
        return datos

    @transaction.atomic
    def save(self):
        User = get_user_model()
        cliente = (
            Cliente.objects.select_for_update()
            .filter(pk=self.cliente_id, usuario__isnull=True)
            .first()
        )
        if cliente is None:
            raise ValidationError(ERROR_DATOS_CLIENTE)

        usuario = User.objects.create_user(
            username=cliente.documento,
            password=self.cleaned_data["password1"],
        )
        grupo_cliente, _ = Group.objects.get_or_create(name="Cliente")
        usuario.groups.add(grupo_cliente)
        cliente.usuario = usuario
        cliente.save(update_fields=["usuario"])
        return usuario

class ReporteForm(forms.Form):
    desde = forms.DateField(
        label="Desde",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    hasta = forms.DateField(
        label="Hasta",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields["desde"].initial = hoy.replace(day=1)
        self.fields["hasta"].initial = hoy

    def clean(self):
        datos = super().clean()
        desde = datos.get("desde")
        hasta = datos.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("hasta", "La fecha final debe ser igual o posterior a la inicial.")
        return datos
