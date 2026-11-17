from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path, reverse
from core.views import pagina_no_encontrada, permiso_denegado


class InicioSesionPorRolView(LoginView):
    def get_success_url(self):
        if self.request.user.groups.filter(name="Cliente").exists():
            return reverse("core:mi_cuenta")
        return super().get_success_url()


handler403 = permiso_denegado
handler404 = pagina_no_encontrada

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/login/', InicioSesionPorRolView.as_view(), name="login"),
    path('cuentas/', include('django.contrib.auth.urls')),
    path('', include('core.urls')),
    path('catalogo/', include('inventario.urls')),
    path('empenos/', include('empenos.urls')),
    path('ventas/', include('ventas.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
