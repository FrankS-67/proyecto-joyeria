from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from core.permisos import AdministradorRequeridoMixin, EmpleadoRequeridoMixin
from inventario.models import TipoOro, calcular_precio_venta

from . import servicios
from .forms import (
    AnularContratoForm,
    ArticuloEmpenoFormSet,
    ClienteForm,
    ContratoCrearForm,
    PagoForm,
    PrecioLiquidacionFormSet,
    SimuladorArticuloFormSet,
    SimuladorEmpenoForm,
)
from .models import Cliente, Contrato


class PanelEmpleadoRequeridoMixin(LoginRequiredMixin, EmpleadoRequeridoMixin):
    pass


class PanelAdministradorRequeridoMixin(LoginRequiredMixin, AdministradorRequeridoMixin):
    pass


class ClienteListaView(PanelEmpleadoRequeridoMixin, ListView):
    model = Cliente
    template_name = "empenos/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(
                models_q_documento_nombre(busqueda)
            )
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["busqueda"] = self.request.GET.get("q", "").strip()
        return contexto


class ClienteCrearView(PanelEmpleadoRequeridoMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "empenos/cliente_form.html"
    success_url = reverse_lazy("empenos:cliente_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente creado correctamente.")
        return super().form_valid(form)


class ClienteEditarView(PanelEmpleadoRequeridoMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "empenos/cliente_form.html"
    success_url = reverse_lazy("empenos:cliente_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente actualizado correctamente.")
        return super().form_valid(form)


class ContratoListaView(PanelEmpleadoRequeridoMixin, ListView):
    model = Contrato
    template_name = "empenos/contrato_list.html"
    context_object_name = "contratos"
    paginate_by = 10

    def get_queryset(self):
        queryset = Contrato.objects.select_related("cliente", "empleado")
        busqueda = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "").strip()
        desde = self.request.GET.get("desde", "").strip()
        if busqueda:
            queryset = queryset.filter(
                models_q_numero_documento(busqueda)
            )
        if estado == "VENCIDO":
            queryset = queryset.filter(
                estado=Contrato.Estado.ACTIVO,
                fecha_vencimiento__lt=timezone.localdate(),
            )
        elif estado:
            queryset = queryset.filter(estado=estado)
            if estado == Contrato.Estado.ACTIVO:
                queryset = queryset.filter(fecha_vencimiento__gte=timezone.localdate())
        if desde:
            try:
                date.fromisoformat(desde)
            except ValueError:
                pass
            else:
                queryset = queryset.filter(fecha_inicio__gte=desde)
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            busqueda=self.request.GET.get("q", ""),
            estado=self.request.GET.get("estado", ""),
            desde=self.request.GET.get("desde", ""),
        )
        return contexto


class ContratoCrearView(PanelEmpleadoRequeridoMixin, TemplateView):
    template_name = "empenos/contrato_form.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.setdefault("form", ContratoCrearForm())
        contexto.setdefault(
            "formset",
            ArticuloEmpenoFormSet(instance=Contrato(), prefix="articulos"),
        )
        contexto["valores_oro_json"] = {
            tipo.pk: str(tipo.valor_prestamo_gramo)
            for tipo in TipoOro.objects.all()
        }
        return contexto

    def post(self, request, *args, **kwargs):
        form = ContratoCrearForm(request.POST)
        formset = ArticuloEmpenoFormSet(
            request.POST, instance=Contrato(), prefix="articulos"
        )
        if form.is_valid() and formset.is_valid():
            articulos = [
                datos
                for datos in formset.cleaned_data
                if datos and not datos.get("DELETE") and datos.get("categoria")
            ]
            try:
                with transaction.atomic():
                    cliente = form.obtener_cliente()
                    contrato = servicios.crear_contrato(
                        {
                            "cliente": cliente,
                            "fecha_inicio": form.cleaned_data["fecha_inicio"],
                            "fecha_vencimiento": form.cleaned_data["fecha_vencimiento"],
                            "valor_prestamo": form.cleaned_data["valor_prestamo"],
                            "observaciones": form.cleaned_data["observaciones"],
                        },
                        articulos,
                        request.user,
                    )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    f"Contrato {contrato.numero_formateado} creado correctamente.",
                )
                return redirect(
                    "empenos:contrato_detalle", numero=contrato.numero
                )

        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )


class ContratoDetalleView(PanelEmpleadoRequeridoMixin, DetailView):
    model = Contrato
    template_name = "empenos/contrato_detalle.html"
    context_object_name = "contrato"
    slug_url_kwarg = "numero"
    slug_field = "numero"

    def get_queryset(self):
        return Contrato.objects.select_related(
            "cliente", "empleado"
        ).prefetch_related("articulos__categoria", "articulos__tipo_oro", "pagos")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        contexto["interes"] = servicios.calcular_interes(self.object, hoy)
        contexto["saldo"] = servicios.calcular_saldo(self.object, hoy)
        contexto["puede_liquidarse"] = (
            self.object.estado == Contrato.Estado.ACTIVO
            and hoy >= servicios.fecha_liquidacion(self.object)
        )
        return contexto


class ContratoImprimirView(ContratoDetalleView):
    template_name = "empenos/contrato_imprimir.html"


class SimuladorEmpenoView(TemplateView):
    template_name = "empenos/simulador.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.setdefault("form", SimuladorEmpenoForm())
        contexto.setdefault(
            "formset",
            SimuladorArticuloFormSet(prefix="articulos"),
        )
        contexto["valores_oro_json"] = {
            tipo.pk: str(tipo.valor_prestamo_gramo)
            for tipo in TipoOro.objects.order_by("nombre")
        }
        return contexto

    def post(self, request, *args, **kwargs):
        form = SimuladorEmpenoForm(request.POST)
        formset = SimuladorArticuloFormSet(
            request.POST, prefix="articulos"
        )
        simulacion = None
        if form.is_valid() and formset.is_valid():
            articulos = [
                datos
                for datos in formset.cleaned_data
                if datos and not datos.get("DELETE") and datos.get("categoria")
            ]
            try:
                simulacion = servicios.simular_empeno(
                    articulos,
                    form.cleaned_data["valor_prestamo"],
                )
            except ValidationError as error:
                form.add_error(None, error)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                formset=formset,
                simulacion=simulacion,
            )
        )


class ContratoPagoView(PanelEmpleadoRequeridoMixin, FormView):
    template_name = "empenos/contrato_pago.html"
    form_class = PagoForm

    @cached_property
    def contrato(self):
        return get_object_or_404(
            Contrato.objects.select_related("cliente"),
            numero=self.kwargs["numero"],
        )

    def get(self, request, *args, **kwargs):
        if self.contrato.estado != Contrato.Estado.ACTIVO:
            messages.error(request, "Solo se registran pagos en contratos activos.")
            return redirect("empenos:contrato_detalle", numero=self.contrato.numero)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.contrato.estado != Contrato.Estado.ACTIVO:
            messages.error(request, "Solo se registran pagos en contratos activos.")
            return redirect("empenos:contrato_detalle", numero=self.contrato.numero)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        contexto["contrato"] = self.contrato
        contexto["interes"] = servicios.calcular_interes(self.contrato, hoy)
        contexto["saldo"] = servicios.calcular_saldo(self.contrato, hoy)
        return contexto

    def form_valid(self, form):
        try:
            servicios.registrar_pago(
                self.contrato,
                form.cleaned_data["monto"],
                form.cleaned_data["tipo"],
                self.request.user,
                form.cleaned_data["observaciones"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Pago registrado correctamente.")
        return redirect("empenos:contrato_detalle", numero=self.contrato.numero)


class ContratoAnularView(PanelAdministradorRequeridoMixin, FormView):
    template_name = "empenos/contrato_anular.html"
    form_class = AnularContratoForm

    @cached_property
    def contrato(self):
        return get_object_or_404(Contrato, numero=self.kwargs["numero"])

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["contrato"] = self.contrato
        return contexto

    def form_valid(self, form):
        try:
            servicios.anular_contrato(
                self.contrato,
                self.request.user,
                form.cleaned_data["observacion"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Contrato anulado correctamente.")
        return redirect("empenos:contrato_detalle", numero=self.contrato.numero)


class ContratoLiquidarView(PanelAdministradorRequeridoMixin, TemplateView):
    template_name = "empenos/contrato_liquidar.html"

    @cached_property
    def contrato(self):
        return get_object_or_404(
            Contrato.objects.prefetch_related("articulos__categoria"),
            numero=self.kwargs["numero"],
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["contrato"] = self.contrato
        contexto["fecha_liquidacion"] = servicios.fecha_liquidacion(self.contrato)
        contexto.setdefault(
            "formset",
            self.crear_formset(initial=self.articulos_iniciales()),
        )
        return contexto

    def articulos_iniciales(self):
        return [
            {
                "articulo_id": articulo.pk,
                "categoria": f"{articulo.categoria} - {articulo.peso_gramos} g",
                "precio_venta": calcular_precio_venta(
                    articulo.tipo_oro, articulo.peso_gramos
                ),
            }
            for articulo in self.contrato.articulos.all()
        ]

    def crear_formset(self, **kwargs):
        return PrecioLiquidacionFormSet(prefix="precios", **kwargs)

    def post(self, request, *args, **kwargs):
        formset = self.crear_formset(data=request.POST)
        if formset.is_valid():
            articulos = list(self.contrato.articulos.all())
            ids_esperados = {articulo.pk for articulo in articulos}
            datos = formset.cleaned_data
            ids_recibidos = [fila["articulo_id"] for fila in datos]
            if len(ids_recibidos) != len(set(ids_recibidos)) or set(ids_recibidos) != ids_esperados:
                formset.add_error(
                    None,
                    "El formulario debe incluir una sola fila por cada artículo del contrato.",
                )
            else:
                precios = {
                    fila["articulo_id"]: fila["precio_venta"]
                    for fila in datos
                }
                try:
                    prendas = servicios.pasar_a_inventario(
                        self.contrato, request.user, precios
                    )
                except ValidationError as error:
                    for mensaje in error.messages:
                        formset.add_error(None, mensaje)
                else:
                    messages.success(
                        request,
                        f"Contrato liquidado; {len(prendas)} prenda(s) pasaron al inventario.",
                    )
                    return redirect(
                        "empenos:contrato_detalle", numero=self.contrato.numero
                    )
        return self.render_to_response(
            self.get_context_data(formset=formset)
        )


def models_q_documento_nombre(busqueda):
    from django.db.models import Q

    return Q(documento__icontains=busqueda) | Q(nombres__icontains=busqueda)


def models_q_numero_documento(busqueda):
    from django.db.models import Q

    filtros = Q(cliente__documento__icontains=busqueda)
    if busqueda.isdigit():
        filtros |= Q(numero=int(busqueda))
    return filtros
