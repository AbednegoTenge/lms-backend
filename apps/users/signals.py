from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.users.models import UserRole


@receiver(post_save, sender=UserRole)
def invalidate_role_cache_on_save(sender, instance, **kwargs):
    instance.user.invalidate_role_cache()


@receiver(post_delete, sender=UserRole)
def invalidate_role_cache_on_delete(sender, instance, **kwargs):
    instance.user.invalidate_role_cache()
