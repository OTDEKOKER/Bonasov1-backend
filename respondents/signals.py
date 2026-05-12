from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Interaction, Response
from .rollups import (
    get_interaction_rollup_context,
    sync_interaction_rollups,
    sync_rollup_bucket,
    sync_response_rollups,
)


@receiver(pre_save, sender=Interaction)
def capture_previous_interaction_rollup_context(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = get_interaction_rollup_context(instance.pk)
    instance._previous_rollup_contexts = [previous] if previous else []


@receiver(post_save, sender=Interaction)
def sync_interaction_rollups_on_save(sender, instance, **kwargs):
    sync_interaction_rollups(
        instance,
        previous_contexts=getattr(instance, '_previous_rollup_contexts', None),
    )


@receiver(post_save, sender=Response)
def sync_response_rollups_on_save(sender, instance, **kwargs):
    sync_response_rollups(instance)


@receiver(pre_delete, sender=Response)
def capture_previous_response_rollup_context(sender, instance, **kwargs):
    instance._previous_rollup_context = get_interaction_rollup_context(instance.interaction_id)


@receiver(post_delete, sender=Response)
def sync_response_rollups_on_delete(sender, instance, **kwargs):
    previous = getattr(instance, '_previous_rollup_context', None)
    if previous:
        sync_rollup_bucket(
            indicator_id=instance.indicator_id,
            project_id=previous.get('project_id'),
            organization_id=previous.get('organization_id'),
            period_date=previous.get('date'),
        )
        return
    sync_response_rollups(instance)
