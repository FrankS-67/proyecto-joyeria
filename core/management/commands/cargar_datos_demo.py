import calendar
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from empenos import servicios as servicios_empeno
from empenos.models import Cliente, Contrato, Pago, RangoInteres
from inventario.models import Categoria, Prenda, TipoOro
from ventas import servicios as servicios_venta


# DEMO: todos estos valores y usuarios son ficticios, solo para desarrollo.
CLAVE_DEMO = "contraseña_demo1"
TIPOS_ORO_DEMO = {
    "Italiano": ("100000.00", "75.00", "300000.00"),
    "Nacional": ("90000.00", "65.00", "280000.00"),
    "14k": ("70000.00", "58.30", "250000.00"),
    "Chino": ("50000.00", "50.00", "200000.00"),
}
CATEGORIAS_DEMO = ("Anillo", "Cadena", "Pulsera", "Arete", "Aro", "Candonga")
USUARIOS_DEMO = (
    ("administrador_demo", "Administrador", True),
    ("empleado_demo", "Empleado", False),
)
CLIENTES_DEMO = (
    (
        "DEMO-CLIENTE-001", "Cliente Demo Uno", "0000000001",
        "Dirección ficticia 1", "cliente_demo_01",
    ),
    (
        "DEMO-CLIENTE-002", "Cliente Demo Dos", "0000000002",
        "Dirección ficticia 2", "cliente_demo_02",
    ),
    (
        "DEMO-CLIENTE-003", "Cliente Demo Tres", "0000000003",
        "Dirección ficticia 3", "cliente_demo_03",
    ),
    (
        "DEMO-CLIENTE-004", "Cliente Demo Cuatro", "0000000004",
        "Dirección ficticia 4", "cliente_demo_04",
    ),
)
PRENDAS_CATALOGO_DEMO = (
    ("DEMO: anillo italiano", "Anillo", "Italiano", "2.50", "875000.00"),
    ("DEMO: cadena nacional", "Cadena", "Nacional", "4.20", "1386000.00"),
    ("DEMO: pulsera nacional", "Pulsera", "Nacional", "3.10", "1023000.00"),
    ("DEMO: candongas italianas", "Candonga", "Italiano", "2.00", "700000.00"),
    ("DEMO: aretes italianos", "Arete", "Italiano", "1.40", "490000.00"),
    ("DEMO: aro nacional", "Aro", "Nacional", "1.80", "594000.00"),
    (
        "DEMO: pulsera de prueba vendida", "Pulsera", "Nacional",
        "2.20", "726000.00",
    ),
)
CONTRATOS_DEMO = (
    (
        "DEMO: contrato activo", "DEMO-CLIENTE-001", "Italiano",
        "Cadena", "3.00", "500000.00", 0,
    ),
    (
        "DEMO: contrato vencido en gracia", "DEMO-CLIENTE-002",
        "Nacional", "Pulsera", "4.00", "600000.00", -5,
    ),
    (
        "DEMO: contrato liquidado", "DEMO-CLIENTE-003", "14k",
        "Anillo", "2.50", "300000.00", -8,
    ),
    (
        "DEMO: contrato retirado", "DEMO-CLIENTE-004", "Chino",
        "Cadena", "3.00", "400000.00", 0,
    ),
)


def _sumar_meses(fecha, meses):
    mes_indice = fecha.month - 1 + meses
    anio = fecha.year + mes_indice // 12
    mes = mes_indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


class Command(BaseCommand):
    help = "Carga datos DEMO ficticios para desarrollo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-demo-passwords",
            action="store_true",
            help="Restablece y muestra la contraseña compartida de las cuentas DEMO.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Este comando DEMO solo se puede ejecutar con DEBUG activo.")

        grupos = {
            nombre: Group.objects.get_or_create(name=nombre)[0]
            for nombre in ("Empleado", "Administrador", "Cliente")
        }
        for nombre, (valor, pureza, valor_prestamo) in TIPOS_ORO_DEMO.items():
            TipoOro.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "valor_gramo": valor,
                    "pureza": pureza,
                    "valor_prestamo_gramo": valor_prestamo,
                },
            )
        for nombre in CATEGORIAS_DEMO:
            Categoria.objects.get_or_create(nombre=nombre)
        RangoInteres.objects.get_or_create(
            monto_desde="0.00",
            defaults={"monto_hasta": None, "tasa_mensual": "5.00"},
        )

        reiniciar_claves = options["reset_demo_passwords"]
        usuarios = {}
        for usuario_nombre, rol, es_staff in USUARIOS_DEMO:
            usuarios[usuario_nombre] = self._obtener_usuario(
                usuario_nombre,
                f"{usuario_nombre}@ejemplo.invalid",
                grupos[rol],
                es_staff,
                reiniciar_claves,
            )

        clientes = {}
        for documento, nombres, telefono, direccion, usuario_nombre in CLIENTES_DEMO:
            usuario = self._obtener_usuario(
                usuario_nombre,
                f"{usuario_nombre}@ejemplo.invalid",
                grupos["Cliente"],
                False,
                reiniciar_claves,
            )
            cliente, _ = Cliente.objects.get_or_create(
                documento=documento,
                defaults={
                    "nombres": nombres,
                    "telefono": telefono,
                    "direccion": direccion,
                },
            )
            if cliente.usuario_id and cliente.usuario_id != usuario.pk:
                raise CommandError(
                    f"El cliente DEMO {documento} ya está vinculado a otra cuenta."
                )
            if cliente.usuario_id is None:
                otro_cliente = Cliente.objects.filter(usuario=usuario).exclude(
                    pk=cliente.pk
                ).first()
                if otro_cliente:
                    raise CommandError(
                        f"La cuenta {usuario_nombre} ya está vinculada a otro cliente."
                    )
                cliente.usuario = usuario
                cliente.save(update_fields=["usuario"])
            clientes[documento] = cliente

        self._crear_prendas_catalogo()
        self._crear_contratos(usuarios["empleado_demo"], clientes)
        self._crear_venta_demo(
            usuarios["empleado_demo"],
            clientes["DEMO-CLIENTE-004"],
        )

        self.stdout.write(self.style.SUCCESS("Datos DEMO cargados (valores ficticios)."))

    def _obtener_usuario(
        self, username, email, grupo, es_staff, reiniciar_claves
    ):
        usuario, creado = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": es_staff,
                "is_active": True,
            },
        )
        campos_actualizados = []
        if usuario.is_staff != es_staff:
            usuario.is_staff = es_staff
            campos_actualizados.append("is_staff")
        if not usuario.is_active:
            usuario.is_active = True
            campos_actualizados.append("is_active")
        if campos_actualizados:
            usuario.save(update_fields=campos_actualizados)

        if creado or reiniciar_claves:
            usuario.set_password(CLAVE_DEMO)
            usuario.save(update_fields=["password"])
            self.stdout.write(
                f"Credencial temporal DEMO para {username}: {CLAVE_DEMO}"
            )
        usuario.groups.add(grupo)
        return usuario

    def _crear_prendas_catalogo(self):
        for descripcion, categoria_nombre, tipo_nombre, peso, precio in PRENDAS_CATALOGO_DEMO:
            prenda = Prenda.objects.filter(descripcion=descripcion).first()
            if prenda is None:
                prenda = Prenda(descripcion=descripcion)
            prenda.categoria = Categoria.objects.get(nombre=categoria_nombre)
            prenda.tipo_oro = TipoOro.objects.get(nombre=tipo_nombre)
            prenda.peso_gramos = Decimal(peso)
            prenda.precio_venta = Decimal(precio)
            prenda.save()

    def _crear_contratos(self, empleado, clientes):
        hoy = timezone.localdate()
        for (
            marca,
            documento_cliente,
            tipo_nombre,
            categoria_nombre,
            peso,
            prestamo,
            meses_desde_inicio,
        ) in CONTRATOS_DEMO:
            contrato = Contrato.objects.filter(
                observaciones__startswith=marca
            ).first()
            if contrato is None:
                fecha_inicio = _sumar_meses(hoy, meses_desde_inicio)
                contrato = servicios_empeno.crear_contrato(
                    {
                        "cliente": clientes[documento_cliente],
                        "fecha_inicio": fecha_inicio,
                        "fecha_vencimiento": _sumar_meses(
                            fecha_inicio, settings.PLAZO_CONTRATO_MESES
                        ),
                        "valor_prestamo": Decimal(prestamo),
                        "observaciones": marca,
                    },
                    [
                        {
                            "categoria": Categoria.objects.get(nombre=categoria_nombre),
                            "tipo_oro": TipoOro.objects.get(nombre=tipo_nombre),
                            "peso_gramos": Decimal(peso),
                            "descripcion": f"Prenda ficticia de prueba ({marca}).",
                        }
                    ],
                    empleado,
                )

            if marca == "DEMO: contrato vencido en gracia":
                if not contrato.pagos.filter(
                    tipo=Pago.Tipo.ABONO,
                    observaciones="Abono DEMO de prueba.",
                ).exists():
                    servicios_empeno.registrar_pago(
                        contrato,
                        Decimal("25000.00"),
                        Pago.Tipo.ABONO,
                        empleado,
                        observaciones="Abono DEMO de prueba.",
                    )
            elif marca == "DEMO: contrato liquidado":
                if contrato.estado == Contrato.Estado.ACTIVO:
                    precios = {
                        articulo.pk: (
                            articulo.valor_calculado * Decimal("1.50")
                        ).quantize(Decimal("0.01"))
                        for articulo in contrato.articulos.all()
                    }
                    servicios_empeno.pasar_a_inventario(
                        contrato, empleado, precios_venta=precios
                    )
            elif marca == "DEMO: contrato retirado":
                if contrato.estado == Contrato.Estado.ACTIVO:
                    servicios_empeno.registrar_pago(
                        contrato,
                        servicios_empeno.calcular_saldo(contrato, hoy),
                        Pago.Tipo.RETIRO,
                        empleado,
                        observaciones="Retiro DEMO de prueba.",
                    )

    def _crear_venta_demo(self, empleado, cliente):
        descripcion = "DEMO: pulsera de prueba vendida"
        prenda = Prenda.objects.filter(descripcion=descripcion).first()
        if prenda and prenda.estado == Prenda.Estado.DISPONIBLE:
            servicios_venta.registrar_venta(
                empleado,
                [{"prenda_id": prenda.pk, "precio_final": prenda.precio_venta}],
                cliente=cliente,
            )
