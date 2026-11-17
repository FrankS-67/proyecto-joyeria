from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from empenos.models import Cliente
from inventario.models import Categoria, Prenda, TipoOro

from .models import DetalleVenta, Venta
from .servicios import registrar_venta


class VentasTests(TestCase):
    def setUp(self):
        self.empleado = User.objects.create_user(username="ventas_empleado")
        self.empleado.groups.add(Group.objects.create(name="Empleado"))
        self.cliente = Cliente.objects.create(
            documento="V-100",
            nombres="Cliente Ventas",
            telefono="3001234567",
        )
        self.categoria = Categoria.objects.create(nombre="Prenda venta")
        self.tipo_oro = TipoOro.objects.create(
            nombre="Italiano", valor_gramo=Decimal("100000")
        )
        self.prendas = [
            Prenda.objects.create(
                categoria=self.categoria,
                tipo_oro=self.tipo_oro,
                peso_gramos=Decimal("1.00"),
                precio_venta=Decimal("200000"),
            )
            for _ in range(2)
        ]

    def test_registra_venta_calcula_total_y_descuenta_inventario(self):
        venta = registrar_venta(
            self.empleado,
            [
                {"prenda_id": self.prendas[0].pk, "precio_final": Decimal("180000")},
                {"prenda_id": self.prendas[1].pk, "precio_final": Decimal("195000")},
            ],
            self.cliente,
        )

        self.assertEqual(venta.total, Decimal("375000"))
        self.assertEqual(venta.detalles.count(), 2)
        self.assertEqual(
            set(
                Prenda.objects.filter(pk__in=[prenda.pk for prenda in self.prendas])
                .values_list("estado", flat=True)
            ),
            {Prenda.Estado.VENDIDA},
        )
        catalogo = self.client.get(reverse("inventario:catalogo"))
        self.assertNotIn(self.prendas[0].pk, [p.pk for p in catalogo.context["prendas"]])
        self.assertNotIn(self.prendas[1].pk, [p.pk for p in catalogo.context["prendas"]])

    def test_prenda_vendida_no_puede_venderse_de_nuevo(self):
        registrar_venta(
            self.empleado,
            [{"prenda_id": self.prendas[0].pk, "precio_final": Decimal("180000")}],
        )

        with self.assertRaises(ValidationError):
            registrar_venta(
                self.empleado,
                [{"prenda_id": self.prendas[0].pk, "precio_final": Decimal("180000")}],
            )

        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(DetalleVenta.objects.count(), 1)

    def test_solo_se_pueden_vender_tipos_italiano_y_nacional(self):
        tipo_chino = TipoOro.objects.create(
            nombre="Chino", valor_gramo=Decimal("100000")
        )
        prenda_china = Prenda.objects.create(
            categoria=self.categoria,
            tipo_oro=tipo_chino,
            peso_gramos=Decimal("1.00"),
            precio_venta=Decimal("200000"),
        )

        with self.assertRaisesRegex(ValidationError, "Italiano o Nacional"):
            registrar_venta(
                self.empleado,
                [{"prenda_id": prenda_china.pk, "precio_final": Decimal("200000")}],
            )

        self.assertFalse(Venta.objects.exists())

    def test_rechaza_prenda_duplicada_en_la_misma_venta(self):
        with self.assertRaises(ValidationError):
            registrar_venta(
                self.empleado,
                [
                    {"prenda_id": self.prendas[0].pk, "precio_final": Decimal("180000")},
                    {"prenda_id": self.prendas[0].pk, "precio_final": Decimal("190000")},
                ],
            )

        self.assertFalse(Venta.objects.exists())
        self.assertEqual(self.prendas[0].estado, Prenda.Estado.DISPONIBLE)

    def test_rechaza_venta_sin_articulos_y_precios_no_positivos(self):
        with self.assertRaises(ValidationError):
            registrar_venta(self.empleado, [])
        with self.assertRaises(ValidationError):
            registrar_venta(
                self.empleado,
                [{"prenda_id": self.prendas[0].pk, "precio_final": Decimal("0")}],
            )
        self.assertFalse(Venta.objects.exists())

    def test_empleado_registra_venta_desde_formulario(self):
        self.client.force_login(self.empleado)
        respuesta = self.client.post(
            reverse("ventas:nueva"),
            {
                "cliente": str(self.cliente.pk),
                "detalles-TOTAL_FORMS": "1",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "1",
                "detalles-MAX_NUM_FORMS": "1000",
                "detalles-0-prenda": str(self.prendas[0].pk),
                "detalles-0-precio_final": "175.000",
            },
        )

        self.assertRedirects(respuesta, reverse("ventas:lista"))
        venta = Venta.objects.get()
        self.assertEqual(venta.total, Decimal("175000"))
        self.prendas[0].refresh_from_db()
        self.assertEqual(self.prendas[0].estado, Prenda.Estado.VENDIDA)

    def test_visitante_no_accede_al_panel_de_ventas(self):
        respuesta = self.client.get(reverse("ventas:lista"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("/cuentas/login/"))
