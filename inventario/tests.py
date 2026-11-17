from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import Group, User
from django.core.management import CommandError, call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import MAXIMO_FOTO_BYTES, PrendaForm
from .models import Categoria, CotizacionOro, Prenda, TipoOro
from .servicios import (
    CotizacionMercado,
    ErrorCotizacionOro,
    actualizar_precios_oro,
    obtener_cotizacion_oro,
)
from ventas.models import DetalleVenta, Venta


class CatalogoTests(TestCase):
    def setUp(self):
        self.categoria_anillo = Categoria.objects.create(nombre="Anillo público")
        self.categoria_cadena = Categoria.objects.create(nombre="Cadena pública")
        self.tipo_oro = TipoOro.objects.create(
            nombre="Italiano", valor_gramo=Decimal("100000")
        )
        self.anillo = Prenda.objects.create(
            categoria=self.categoria_anillo,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("2.00"),
            precio_venta=Decimal("200000"),
        )
        self.cadena = Prenda.objects.create(
            categoria=self.categoria_cadena,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("3.00"),
            precio_venta=Decimal("300000"),
        )
        self.vendida = Prenda.objects.create(
            categoria=self.categoria_anillo,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("1.00"),
            precio_venta=Decimal("100000"),
            estado=Prenda.Estado.VENDIDA,
        )

    def test_catalogo_muestra_solo_disponibles_y_filtra_categoria_y_oro(self):
        respuesta = self.client.get(
            reverse("inventario:catalogo"),
            {"categoria": self.categoria_anillo.pk, "tipo_oro": self.tipo_oro.pk},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            list(respuesta.context["prendas"]),
            [self.anillo],
        )

    def test_detalle_publico_no_expone_prenda_vendida(self):
        disponible = self.client.get(
            reverse("inventario:prenda_detalle", args=[self.anillo.pk])
        )
        vendida = self.client.get(
            reverse("inventario:prenda_detalle", args=[self.vendida.pk])
        )

        self.assertEqual(disponible.status_code, 200)
        self.assertEqual(vendida.status_code, 404)

    def test_catalogo_solo_publica_italiano_y_nacional_con_descripcion_sencilla(self):
        tipo_nacional = TipoOro.objects.create(
            nombre="Nacional", valor_gramo=Decimal("100000")
        )
        tipo_chino = TipoOro.objects.create(
            nombre="Chino", valor_gramo=Decimal("100000")
        )
        prenda_no_vendible = Prenda.objects.create(
            categoria=self.categoria_anillo,
            tipo_oro=tipo_chino,
            peso_gramos=Decimal("1.00"),
            precio_venta=Decimal("100000"),
        )

        respuesta = self.client.get(reverse("inventario:catalogo"))

        ids_publicados = {prenda.pk for prenda in respuesta.context["prendas"]}
        self.assertIn(self.anillo.pk, ids_publicados)
        self.assertNotIn(prenda_no_vendible.pk, ids_publicados)
        self.assertContains(respuesta, "Anillo público</h2>")
        self.assertContains(respuesta, "2.00 g · Oro Italiano")
        self.assertNotContains(respuesta, "Anillo público de Italiano")
        self.assertNotContains(respuesta, "Chino")
        self.assertEqual(
            set(respuesta.context["tipos_oro"]),
            {self.tipo_oro, tipo_nacional},
        )

    def test_precio_de_catalogo_se_calcula_por_gramo_al_guardar(self):
        nacional = TipoOro.objects.create(
            nombre="Nacional", valor_gramo=Decimal("100000")
        )

        prenda = Prenda.objects.create(
            categoria=self.categoria_cadena,
            tipo_oro=nacional,
            peso_gramos=Decimal("2.50"),
            precio_venta=Decimal("1.00"),
        )

        self.assertEqual(prenda.precio_venta, Decimal("825000.00"))
        prenda.refresh_from_db()
        self.assertEqual(prenda.precio_venta, Decimal("825000.00"))

    def test_gestion_prendas_requiere_administrador(self):
        respuesta_visitante = self.client.get(reverse("inventario:gestion_lista"))
        self.assertEqual(respuesta_visitante.status_code, 302)

        empleado = User.objects.create_user(username="inventario_empleado")
        empleado.groups.add(Group.objects.create(name="Empleado"))
        self.client.force_login(empleado)
        respuesta_empleado = self.client.get(reverse("inventario:gestion_lista"))
        self.assertEqual(respuesta_empleado.status_code, 403)

        administrador = User.objects.create_user(username="inventario_admin")
        administrador.groups.add(Group.objects.create(name="Administrador"))
        self.client.force_login(administrador)
        respuesta_admin = self.client.get(reverse("inventario:gestion_lista"))
        self.assertEqual(respuesta_admin.status_code, 200)

    def test_administrador_crea_prenda_desde_formulario(self):
        administrador = User.objects.create_user(username="admin_crear_prenda")
        administrador.groups.add(Group.objects.create(name="Administrador"))
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("inventario:prenda_crear"),
            {
                "categoria": self.categoria_anillo.pk,
                "tipo_oro": self.tipo_oro.pk,
                "peso_gramos": "4.25",
                "descripcion": "Prenda de prueba",
                "estado": Prenda.Estado.DISPONIBLE,
                "origen": Prenda.Origen.COMPRA,
                "articulo_origen": "",
                "foto-clear": "",
            },
        )

        self.assertRedirects(respuesta, reverse("inventario:gestion_lista"))
        prenda = Prenda.objects.get(descripcion="Prenda de prueba")
        self.assertEqual(prenda.precio_venta, Decimal("1487500.00"))

    def test_formulario_no_admite_prenda_china_para_venta(self):
        tipo_chino = TipoOro.objects.create(
            nombre="Chino", valor_gramo=Decimal("100000")
        )

        form = PrendaForm(
            data={
                "categoria": self.categoria_anillo.pk,
                "tipo_oro": tipo_chino.pk,
                "peso_gramos": "1.00",
                "descripcion": "Prenda no vendible",
                "estado": Prenda.Estado.DISPONIBLE,
                "origen": Prenda.Origen.COMPRA,
                "articulo_origen": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("tipo_oro", form.errors)

    def test_prenda_con_venta_no_se_puede_eliminar(self):
        administrador = User.objects.create_user(username="admin_borrar_prenda")
        administrador.groups.add(Group.objects.create(name="Administrador"))
        venta = Venta.objects.create(empleado=administrador, total=Decimal("200000"))
        DetalleVenta.objects.create(
            venta=venta,
            prenda=self.anillo,
            precio_final=Decimal("200000"),
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("inventario:prenda_eliminar", args=[self.anillo.pk])
        )

        self.assertRedirects(respuesta, reverse("inventario:gestion_lista"))
        self.assertTrue(Prenda.objects.filter(pk=self.anillo.pk).exists())

    def test_foto_supera_limite_se_rechaza(self):
        archivo = SimpleUploadedFile(
            "foto.png",
            b"x" * (MAXIMO_FOTO_BYTES + 1),
            content_type="image/png",
        )
        datos = {
            "categoria": self.categoria_anillo.pk,
            "tipo_oro": self.tipo_oro.pk,
            "peso_gramos": "1.00",
            "precio_venta": "100000.00",
            "estado": Prenda.Estado.DISPONIBLE,
            "origen": Prenda.Origen.COMPRA,
            "articulo_origen": "",
        }
        form = PrendaForm(data=datos, files={"foto": archivo})

        self.assertFalse(form.is_valid())
        self.assertIn("foto", form.errors)


class PreciosOroTests(TestCase):
    def test_actualiza_tarifas_con_pureza_y_margen_confirmados(self):
        tipos = [
            ("Italiano", "75.00", "300000.00", "285000.00"),
            ("Nacional", "65.00", "260000.00", "247000.00"),
            ("14k", "58.30", "233200.00", "221540.00"),
            ("Chino", "50.00", "200000.00", "190000.00"),
        ]
        objetos = [
            TipoOro.objects.create(
                nombre=nombre,
                pureza=Decimal(pureza),
                valor_gramo=Decimal("1.00"),
            )
            for nombre, pureza, _, _ in tipos
        ]
        fecha = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

        registro = actualizar_precios_oro(
            CotizacionMercado(Decimal("400000.00"), fecha)
        )

        self.assertEqual(registro.precio_24k_gramo_cop, Decimal("400000.00"))
        self.assertEqual(registro.fecha_cotizacion, fecha)
        for tipo, (_, _, valor_esperado, compra_esperada) in zip(objetos, tipos):
            tipo.refresh_from_db()
            self.assertEqual(tipo.valor_gramo, Decimal(valor_esperado))
            self.assertEqual(tipo.precio_compra_gramo, Decimal(compra_esperada))
            self.assertEqual(tipo.historial_precios.count(), 1)

    @override_settings(GOLDAPI_TOKEN="")
    def test_requiere_token_de_goldapi(self):
        with self.assertRaisesRegex(ErrorCotizacionOro, "GOLDAPI_TOKEN"):
            obtener_cotizacion_oro()

    @override_settings(GOLDAPI_TOKEN="token-de-prueba")
    @patch("inventario.servicios.urlopen")
    def test_consulta_xau_cop_y_lee_el_precio_por_gramo(self, urlopen_mock):
        respuesta = Mock()
        respuesta.__enter__ = Mock(return_value=respuesta)
        respuesta.__exit__ = Mock(return_value=False)
        respuesta.read.return_value = (
            b'{"timestamp":1794859200,"price_per_unit":{"gram":123456.78}}'
        )
        urlopen_mock.return_value = respuesta

        cotizacion = obtener_cotizacion_oro()

        self.assertEqual(cotizacion.precio_24k_gramo_cop, Decimal("123456.78"))
        solicitud = urlopen_mock.call_args.args[0]
        self.assertEqual(solicitud.full_url, "https://www.goldapi.io/api/price/XAU/COP")
        self.assertEqual(solicitud.get_header("X-access-token"), "token-de-prueba")

    @override_settings(GOLDAPI_TOKEN="")
    def test_comando_reporta_falta_de_configuracion(self):
        with self.assertRaisesRegex(CommandError, "GOLDAPI_TOKEN"):
            call_command("actualizar_precios_oro")

        self.assertEqual(CotizacionOro.objects.count(), 0)
