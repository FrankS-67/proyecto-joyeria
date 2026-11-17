from django import template

register = template.Library()


@register.filter
def en_grupo(usuario, nombre_grupo):
    return usuario.groups.filter(name=nombre_grupo).exists()
