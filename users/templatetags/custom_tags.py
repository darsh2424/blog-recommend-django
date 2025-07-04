from django import template
from django.utils.text import slugify

register = template.Library()

@register.filter
def slugify_value(value):
    return slugify(value)
