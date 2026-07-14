from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.fees.models import FeeStructure, Payment, StudentFee


@receiver(post_save, sender=Payment)
def update_student_fee_on_payment(sender, instance, created, **kwargs):
    if not created:
        return
    from django.db.models import Sum

    with transaction.atomic():
        # Lock the StudentFee row so concurrent payments can't read a stale
        # amount_paid total and clobber each other's update.
        sf = StudentFee.objects.select_for_update().get(pk=instance.student_fee_id)

        total = (
            Payment.objects
            .filter(student_fee_id=instance.student_fee_id)
            .aggregate(total=Sum('amount'))
        )['total'] or 0

        sf.amount_paid = total
        sf.save()  # recomputes payment_status via save() override


@receiver(post_save, sender=FeeStructure)
def invalidate_fee_structure_cache_on_save(sender, instance, **kwargs):
    _invalidate_cache(instance)


@receiver(post_delete, sender=FeeStructure)
def invalidate_fee_structure_cache_on_delete(sender, instance, **kwargs):
    _invalidate_cache(instance)


def _invalidate_cache(instance):
    from django.core.cache import cache

    try:
        cache.delete_pattern(f'fee_structure:{instance.level_id}:*')
    except Exception:
        pass
