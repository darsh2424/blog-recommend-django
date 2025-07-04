from django import template
from django.utils.html import strip_tags
import html

register = template.Library()

@register.filter
def clean_text(value):
    return html.unescape(strip_tags(value))