from django.db.models.signals import pre_save
from django.dispatch import receiver
from blog.models import  Post, PostStatusHistory
from users.models import User, UserStatusHistory


@receiver(pre_save, sender=User)
def log_user_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return  
    try:
        old = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return
    if old.status != instance.status:
        UserStatusHistory.objects.create(
            user=instance,
            old_status=old.status,
            new_status=instance.status,
            changed_by=None  
        )


@receiver(pre_save, sender=Post)
def log_post_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return  
    try:
        old = Post.objects.get(pk=instance.pk)
    except Post.DoesNotExist:
        return
    if old.status != instance.status:
        PostStatusHistory.objects.create(
            post=instance,
            old_status=old.status,
            new_status=instance.status,
            changed_by=None
        )
