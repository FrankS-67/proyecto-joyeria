from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.permisos import AdministradorRequeridoMixin

from .forms import PrendaForm
from .models import Categoria, Prenda, TipoOro, TIPOS_ORO_VENDIBLES


class CatalogoListaView(ListView):
    model = Prenda
    template_name = "inventario/catalogo.html"
    context_object_name = "prendas"
    paginate_by = 12

    def get_queryset(self):
        queryset = Prenda.objects.filter(
            estado=Prenda.Estado.DISPONIBLE,
            tipo_oro__nombre__in=TIPOS_ORO_VENDIBLES,
        ).select_related("categoria", "tipo_oro")
        categoria = self.request.GET.get("categoria", "").strip()
        tipo_oro = self.request.GET.get("tipo_oro", "").strip()
        if categoria.isdigit():
            queryset = queryset.filter(categoria_id=int(categoria))
        if tipo_oro.isdigit():
            queryset = queryset.filter(tipo_oro_id=int(tipo_oro))
        return queryset

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["categorias"] = Categoria.objects.order_by("nombre")
        contexto["tipos_oro"] = TipoOro.objects.filter(
            nombre__in=TIPOS_ORO_VENDIBLES
        ).order_by("nombre")
        contexto["categoria_seleccionada"] = self.request.GET.get("categoria", "")
        contexto["tipo_oro_seleccionado"] = self.request.GET.get("tipo_oro", "")
        return contexto


class CatalogoDetalleView(DetailView):
    model = Prenda
    template_name = "inventario/prenda_detalle.html"
    context_object_name = "prenda"

    def get_queryset(self):
        return Prenda.objects.filter(
            estado=Prenda.Estado.DISPONIBLE,
            tipo_oro__nombre__in=TIPOS_ORO_VENDIBLES,
        ).select_related("categoria", "tipo_oro")


class AdministradorPanelMixin(LoginRequiredMixin, AdministradorRequeridoMixin):
    pass


class PrendaGestionListaView(AdministradorPanelMixin, ListView):
    model = Prenda
    template_name = "inventario/gestion_lista.html"
    context_object_name = "prendas"
    paginate_by = 10

    def get_queryset(self):
        return Prenda.objects.select_related("categoria", "tipo_oro")


class PrendaCrearView(AdministradorPanelMixin, CreateView):
    model = Prenda
    form_class = PrendaForm
    template_name = "inventario/prenda_form.html"
    success_url = reverse_lazy("inventario:gestion_lista")

    def form_valid(self, form):
        messages.success(self.request, "Prenda creada correctamente.")
        return super().form_valid(form)


class PrendaEditarView(AdministradorPanelMixin, UpdateView):
    model = Prenda
    form_class = PrendaForm
    template_name = "inventario/prenda_form.html"
    success_url = reverse_lazy("inventario:gestion_lista")

    def form_valid(self, form):
        messages.success(self.request, "Prenda actualizada correctamente.")
        return super().form_valid(form)


class PrendaEliminarView(AdministradorPanelMixin, DeleteView):
    model = Prenda
    template_name = "inventario/prenda_confirmar_eliminar.html"
    success_url = reverse_lazy("inventario:gestion_lista")

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                "No se puede eliminar una prenda vinculada a una venta o a un empeño.",
            )
            return redirect(self.success_url)
        messages.success(self.request, "Prenda eliminada correctamente.")
        return response
