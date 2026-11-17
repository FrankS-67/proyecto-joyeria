from decimal import Decimal
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from empenos.models import Cliente, Contrato
from inventario.models import Categoria, CotizacionOro, Prenda, TipoOro
from ventas.models import Venta


class RolesTests(TestCase):
    def test_crear_roles_es_idempotente(self):
        call_command("crear_roles", stdout=StringIO())
        call_command("crear_roles", stdout=StringIO())

        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)),
            {"Empleado", "Administrador", "Cliente"},
        )

    def test_superusuario_puede_entrar_al_admin(self):
        usuario = User.objects.create_superuser("administrador", "admin@example.invalid", "clave")
        self.client.force_login(usuario)

        respuesta = self.client.get("/admin/")

        self.assertEqual(respuesta.status_code, 200)


class PermisosTests(TestCase):
    def test_visitante_va_al_login_y_empleado_ve_contratos(self):
        respuesta = self.client.get("/empenos/contratos/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("/cuentas/login/"))

        usuario = User.objects.create_user(username="empleado", password="clave")
        usuario.groups.add(Group.objects.create(name="Empleado"))
        self.client.force_login(usuario)

        respuesta = self.client.get("/empenos/contratos/")

        self.assertEqual(respuesta.status_code, 200)

    def test_acciones_administrativas_rechazan_empleado(self):
        usuario = User.objects.create_user(username="empleado_sin_admin")
        usuario.groups.add(Group.objects.create(name="Empleado"))
        self.client.force_login(usuario)

        respuesta = self.client.get("/empenos/contratos/1/anular/")

        self.assertEqual(respuesta.status_code, 403)

    def test_acciones_administrativas_requieren_autenticacion(self):
        respuesta = self.client.get("/empenos/contratos/1/liquidar/")

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("/cuentas/login/"))


@override_settings(DEBUG=True)
class DatosDemoTests(TestCase):
    def test_cargar_datos_demo_crea_datos_y_usuarios(self):
        salida = StringIO()
        call_command("cargar_datos_demo", stdout=salida)
        call_command("cargar_datos_demo", stdout=StringIO())

        from empenos.models import RangoInteres
        from inventario.models import Categoria, Prenda, TipoOro
        from ventas.models import Venta

        self.assertEqual(TipoOro.objects.count(), 4)
        self.assertEqual(Categoria.objects.count(), 6)
        self.assertEqual(RangoInteres.objects.count(), 1)
        self.assertEqual(Cliente.objects.count(), 4)
        self.assertEqual(Contrato.objects.count(), 4)
        self.assertEqual(Prenda.objects.count(), 8)
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(User.objects.count(), 6)
        for username in (
            "cliente_demo_01",
            "cliente_demo_02",
            "cliente_demo_03",
            "cliente_demo_04",
        ):
            usuario = User.objects.get(username=username)
            self.assertTrue(usuario.groups.filter(name="Cliente").exists())
            self.assertIsNotNone(usuario.perfil_cliente)
        self.assertIn("Credencial temporal DEMO", salida.getvalue())

    def test_resetear_claves_demo_muestra_credenciales_validas(self):
        salida = StringIO()
        call_command(
            "cargar_datos_demo",
            "--reset-demo-passwords",
            stdout=salida,
        )

        credenciales = dict(
            linea.removeprefix("Credencial temporal DEMO para ").split(": ", 1)
            for linea in salida.getvalue().splitlines()
            if linea.startswith("Credencial temporal DEMO para ")
        )
        self.assertEqual(len(credenciales), 6)
        for username, password in credenciales.items():
            self.assertTrue(User.objects.get(username=username).check_password(password))


class MiCuentaTests(TestCase):
    def setUp(self):
        grupo_cliente = Group.objects.create(name="Cliente")
        self.usuario = User.objects.create_user(
            username="cliente_portal",
            password="ClaveDemo123!",
        )
        self.usuario.groups.add(grupo_cliente)
        self.cliente = Cliente.objects.create(
            usuario=self.usuario,
            documento="DEMO-PORTAL-1",
            nombres="Cliente Portal Demo",
            telefono="0000000001",
            direccion="Dirección ficticia",
        )

        usuario_ajeno = User.objects.create_user(username="otro_cliente")
        usuario_ajeno.groups.add(grupo_cliente)
        cliente_ajeno = Cliente.objects.create(
            usuario=usuario_ajeno,
            documento="DEMO-PORTAL-2",
            nombres="Otro Cliente Privado",
            telefono="0000000002",
        )
        empleado = User.objects.create_user(username="empleado_portal")
        self.hoy = timezone.localdate()
        self.contrato_propio = Contrato.objects.create(
            numero=910001,
            cliente=self.cliente,
            empleado=empleado,
            fecha_inicio=self.hoy,
            fecha_vencimiento=self.hoy + timedelta(days=120),
            valor_prestamo=Decimal("100000.00"),
            tasa_aplicada=Decimal("5.00"),
        )
        self.contrato_ajeno = Contrato.objects.create(
            numero=910002,
            cliente=cliente_ajeno,
            empleado=empleado,
            fecha_inicio=self.hoy,
            fecha_vencimiento=self.hoy + timedelta(days=120),
            valor_prestamo=Decimal("200000.00"),
            tasa_aplicada=Decimal("5.00"),
        )

    def test_cliente_ve_solo_sus_contratos(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("core:mi_cuenta"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.contrato_propio.numero_formateado)
        self.assertNotContains(respuesta, self.contrato_ajeno.numero_formateado)
        self.assertNotContains(respuesta, "Otro Cliente Privado")
        self.assertEqual(list(respuesta.context["contratos"]), [self.contrato_propio])

    def test_cliente_no_accede_al_panel_de_empleados(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("empenos:contrato_list"))

        self.assertEqual(respuesta.status_code, 403)

    def test_inicio_de_sesion_redirige_al_portal_del_cliente(self):
        respuesta = self.client.post(
            reverse("login"),
            {"username": "cliente_portal", "password": "ClaveDemo123!"},
        )

        self.assertRedirects(
            respuesta,
            reverse("core:mi_cuenta"),
            fetch_redirect_response=False,
        )


class RegistroClienteTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            documento="REG-CLIENTE-1",
            nombres="Cliente para registro",
            telefono="3001234567",
        )
        self.password = "Brisa-verde-2026!"

    def datos_registro(self, **cambios):
        datos = {
            "documento": self.cliente.documento,
            "telefono": self.cliente.telefono,
            "password1": self.password,
            "password2": self.password,
        }
        datos.update(cambios)
        return datos

    def test_cliente_previamente_registrado_puede_crear_su_cuenta(self):
        respuesta = self.client.post(
            reverse("core:registro_cliente"),
            self.datos_registro(),
        )

        self.assertRedirects(respuesta, reverse("login"))
        self.cliente.refresh_from_db()
        usuario = self.cliente.usuario
        self.assertEqual(usuario.username, self.cliente.documento)
        self.assertTrue(usuario.check_password(self.password))
        self.assertTrue(usuario.groups.filter(name="Cliente").exists())
        self.assertTrue(
            self.client.login(username=self.cliente.documento, password=self.password)
        )
        self.assertEqual(
            self.client.get(reverse("core:mi_cuenta")).status_code,
            200,
        )

    def test_documento_y_telefono_deben_coincidir_con_el_registro(self):
        respuesta = self.client.post(
            reverse("core:registro_cliente"),
            self.datos_registro(telefono="3000000000"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No fue posible validar los datos.")
        self.assertEqual(User.objects.count(), 0)
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.usuario)

    def test_no_permite_registrar_una_segunda_cuenta_para_el_cliente(self):
        usuario = User.objects.create_user(username="cuenta_existente")
        self.cliente.usuario = usuario
        self.cliente.save(update_fields=["usuario"])

        respuesta = self.client.post(
            reverse("core:registro_cliente"),
            self.datos_registro(),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No fue posible validar los datos.")
        self.assertEqual(User.objects.count(), 1)

    def test_inicio_de_sesion_enlaza_al_registro_de_clientes(self):
        respuesta = self.client.get(reverse("login"))

        self.assertContains(
            respuesta,
            reverse("core:registro_cliente"),
        )


class FormatoMonedaTests(TestCase):
    def test_formatea_pesos_con_separador_de_miles(self):
        from core.templatetags.moneda import moneda

        self.assertEqual(moneda(Decimal("1234567.89")), "$ 1.234.568")


class HomePublicoTests(TestCase):
    def test_home_muestra_tarifas_de_compra_con_cotizacion_y_pureza(self):
        Categoria.objects.create(nombre="Anillo para home")
        tipo = TipoOro.objects.create(
            nombre="Italiano para home",
            pureza=Decimal("75.00"),
            valor_gramo=Decimal("123456"),
            precio_compra_gramo=Decimal("117283.20"),
        )
        CotizacionOro.objects.create(
            precio_24k_gramo_cop=Decimal("173000"),
            fecha_cotizacion=timezone.now(),
        )

        respuesta = self.client.get(reverse("core:home"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Anillo para home")
        self.assertContains(respuesta, "Italiano para home")
        self.assertContains(respuesta, "117.283")
        self.assertNotContains(respuesta, "123.456")
        self.assertContains(respuesta, "75,00%")
        self.assertEqual(list(respuesta.context["tipos_oro"]), [tipo])

    def test_home_no_publica_precios_demo_antes_de_la_primera_cotizacion(self):
        TipoOro.objects.create(
            nombre="Tipo sin cotización", valor_gramo=Decimal("123456")
        )

        respuesta = self.client.get(reverse("core:home"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "123.456")
        self.assertContains(
            respuesta,
            "Las tarifas estarán disponibles cuando se consulte la primera cotización",
        )


class ReportesTests(TestCase):
    def setUp(self):
        self.administrador = User.objects.create_user(username="admin_reportes")
        self.administrador.groups.add(Group.objects.create(name="Administrador"))
        self.empleado = User.objects.create_user(username="empleado_reportes")
        self.empleado.groups.add(Group.objects.create(name="Empleado"))
        self.cliente = Cliente.objects.create(
            documento="REP-1", nombres="Cliente Reportes", telefono="3001234567"
        )
        self.hoy = timezone.localdate()
        self.contrato_activo = Contrato.objects.create(
            numero=901,
            cliente=self.cliente,
            empleado=self.empleado,
            fecha_inicio=self.hoy,
            fecha_vencimiento=self.hoy + timedelta(days=30),
            valor_prestamo=Decimal("100000"),
            tasa_aplicada=Decimal("5.00"),
        )
        self.contrato_vencido = Contrato.objects.create(
            numero=902,
            cliente=self.cliente,
            empleado=self.empleado,
            fecha_inicio=self.hoy - timedelta(days=90),
            fecha_vencimiento=self.hoy - timedelta(days=1),
            valor_prestamo=Decimal("200000"),
            tasa_aplicada=Decimal("5.00"),
        )
        self.venta = Venta.objects.create(
            empleado=self.empleado,
            cliente=self.cliente,
            total=Decimal("345678"),
        )

    def test_reporte_muestra_contratos_y_ventas_en_rango(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("core:reportes"),
            {
                "desde": self.hoy.isoformat(),
                "hasta": self.hoy.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_contratos_activos"], 1)
        self.assertEqual(respuesta.context["total_contratos_vencidos"], 1)
        self.assertEqual(respuesta.context["cantidad_ventas"], 1)
        self.assertEqual(respuesta.context["total_ventas"], Decimal("345678"))
        self.assertContains(respuesta, self.contrato_activo.numero_formateado)
        self.assertContains(respuesta, self.contrato_vencido.numero_formateado)

    def test_reporte_rechaza_rango_de_fechas_invertido(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("core:reportes"),
            {
                "desde": (self.hoy + timedelta(days=1)).isoformat(),
                "hasta": self.hoy.isoformat(),
            },
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertContains(
            respuesta,
            "La fecha final debe ser igual o posterior a la inicial.",
            status_code=400,
        )

    def test_reporte_requiere_administrador(self):
        respuesta_publica = self.client.get(reverse("core:reportes"))
        self.assertEqual(respuesta_publica.status_code, 302)

        self.client.force_login(self.empleado)
        respuesta_empleado = self.client.get(reverse("core:reportes"))
        self.assertEqual(respuesta_empleado.status_code, 403)


@override_settings(DEBUG=False)
class PaginasErrorTests(TestCase):
    def test_pagina_404_personalizada(self):
        respuesta = self.client.get("/ruta-inexistente/")

        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(respuesta, "No encontramos esta página", status_code=404)

    def test_pagina_403_personalizada(self):
        usuario = User.objects.create_user(username="empleado_403")
        usuario.groups.add(Group.objects.create(name="Empleado"))
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("core:reportes"))

        self.assertEqual(respuesta.status_code, 403)
        self.assertContains(
            respuesta,
            "No tienes permiso para acceder a esta página",
            status_code=403,
        )
