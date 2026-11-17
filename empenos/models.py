from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Cliente(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_cliente",
        verbose_name="cuenta de acceso",
    )
    documento = models.CharField("documento", max_length=30, unique=True)
    nombres = models.CharField("nombres", max_length=150)
    telefono = models.CharField("teléfono", max_length=30)
    direccion = models.CharField("dirección", max_length=200, blank=True)
    creado = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        ordering = ["nombres", "documento"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self):
        return f"{self.nombres} ({self.documento})"


class RangoInteres(models.Model):
    monto_desde = models.DecimalField(
        "monto desde", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    monto_hasta = models.DecimalField(
        "monto hasta", max_digits=14, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    tasa_mensual = models.DecimalField(
        "tasa mensual (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["monto_desde"]
        verbose_name = "rango de interés"
        verbose_name_plural = "rangos de interés"

    def __str__(self):
        hasta = self.monto_hasta if self.monto_hasta is not None else "sin tope"
        return f"{self.monto_desde} - {hasta}: {self.tasa_mensual}%"

    def clean(self):
        super().clean()
        errores = {}
        if (
            self.monto_desde is not None
            and self.monto_hasta is not None
            and self.monto_desde >= self.monto_hasta
        ):
            errores["monto_hasta"] = "Debe ser mayor que el monto inicial."
        if self.monto_desde is not None:
            rangos = type(self).objects.exclude(pk=self.pk)
            for rango in rangos:
                se_solapan = (
                    (rango.monto_hasta is None or self.monto_desde <= rango.monto_hasta)
                    and (self.monto_hasta is None or rango.monto_desde <= self.monto_hasta)
                )
                if se_solapan:
                    errores["monto_desde"] = "El rango se solapa con otro existente."
                    break
        if errores:
            raise ValidationError(errores)


class Contrato(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        RETIRADO = "RETIRADO", "Retirado"
        LIQUIDADO = "LIQUIDADO", "Liquidado"
        ANULADO = "ANULADO", "Anulado"

    numero = models.PositiveIntegerField("número", unique=True)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="contratos",
        verbose_name="cliente",
    )
    empleado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="contratos_atendidos", verbose_name="empleado",
    )
    fecha_inicio = models.DateField("fecha de inicio", default=timezone.localdate)
    fecha_vencimiento = models.DateField("fecha de vencimiento")
    valor_prestamo = models.DecimalField(
        "valor del préstamo", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tasa_aplicada = models.DecimalField(
        "tasa aplicada (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    estado = models.CharField(
        "estado", max_length=10, choices=Estado.choices, default=Estado.ACTIVO,
    )
    observaciones = models.TextField("observaciones", blank=True)
    creado = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        ordering = ["-numero"]
        verbose_name = "contrato"
        verbose_name_plural = "contratos"

    def __str__(self):
        return self.numero_formateado

    @property
    def numero_formateado(self):
        return f"{self.numero:06d}"

    def clean(self):
        super().clean()
        if self.fecha_inicio and self.fecha_vencimiento and self.fecha_vencimiento <= self.fecha_inicio:
            raise ValidationError({
                "fecha_vencimiento": "Debe ser posterior a la fecha de inicio."
            })

    @property
    def esta_vencido(self):
        return self.estado == self.Estado.ACTIVO and self.fecha_vencimiento < timezone.localdate()

    @property
    def valor_calculado_total(self):
        from decimal import Decimal

        return sum(
            (articulo.valor_calculado for articulo in self.articulos.all()),
            Decimal("0.00"),
        )


class ArticuloEmpeno(models.Model):
    contrato = models.ForeignKey(
        Contrato, on_delete=models.CASCADE, related_name="articulos",
        verbose_name="contrato",
    )
    categoria = models.ForeignKey(
        "inventario.Categoria", on_delete=models.PROTECT, verbose_name="categoría",
    )
    tipo_oro = models.ForeignKey(
        "inventario.TipoOro", on_delete=models.PROTECT, verbose_name="tipo de oro",
    )
    peso_gramos = models.DecimalField(
        "peso en gramos", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    valor_gramo_aplicado = models.DecimalField(
        "valor por gramo aplicado", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    descripcion = models.TextField("descripción", blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "artículo empeñado"
        verbose_name_plural = "artículos empeñados"

    def __str__(self):
        return f"{self.categoria}: {self.peso_gramos} g"

    @property
    def valor_calculado(self):
        return self.peso_gramos * self.valor_gramo_aplicado


class Pago(models.Model):
    class Tipo(models.TextChoices):
        ABONO = "ABONO", "Abono"
        RENOVACION = "RENOVACION", "Renovación"
        RETIRO = "RETIRO", "Retiro"

    contrato = models.ForeignKey(
        Contrato, on_delete=models.PROTECT, related_name="pagos",
        verbose_name="contrato",
    )
    fecha = models.DateTimeField("fecha", default=timezone.now)
    monto = models.DecimalField(
        "monto", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices)
    empleado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="pagos_registrados", verbose_name="empleado",
    )
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "pago"
        verbose_name_plural = "pagos"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.monto}"
