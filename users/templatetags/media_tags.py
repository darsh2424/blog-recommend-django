from django import template
from django.conf import settings
import os

register = template.Library()

@register.filter
def resolve_media_url(value):
    if not value:
        return 'https://via.placeholder.com/250x200?text=No+Image'
    
    # If it's already a full URL (http/https)
    if value.startswith(('http://', 'https://')):
        return value
    
    # If it's a local media file path
    if value.startswith('images/'):  # or whatever prefix you use
        return os.path.join(settings.MEDIA_URL, value)
    
    return value