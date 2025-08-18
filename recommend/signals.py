from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from blog.models import Post
from users.models import PostInteraction
import time

@receiver([post_save, post_delete], sender=PostInteraction)
def invalidate_user_cache(sender, instance, **kwargs):
    def _invalidate():
        cache.delete(f'user_recs_{instance.user_id}')
        cache.set(f'user_{instance.user_id}_updated', time.time())
    transaction.on_commit(_invalidate)

@receiver([post_save, post_delete], sender=Post)
def invalidate_global_cache(sender, instance, **kwargs):
    def _invalidate():
        cache.set('global_data_updated', time.time())
    transaction.on_commit(_invalidate)
