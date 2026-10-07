import logging
from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import IdeaSubmission, IdeaDraft, PendingFileDeletion
from .storage import draft_storage

logger = logging.getLogger(__name__)


def attempt_deletion(job):
    storage = draft_storage if job.private else IdeaSubmission._meta.get_field("idea_pdf").storage
    model, field = (IdeaDraft, "pdf") if job.private else (IdeaSubmission, "idea_pdf")
    if model.objects.filter(**{field: job.name}).exists():
        return
    try:
        storage.delete(job.name)
    except Exception:
        logger.exception("Falha na limpeza do arquivo; tarefa %s será repetida", job.pk)
    else:
        job.delete()


def queue_deletion(name, private=False):
    if name:
        job = PendingFileDeletion.objects.create(name=name, private=private)
        transaction.on_commit(lambda: attempt_deletion(job))


@receiver(post_delete, sender=IdeaSubmission)
@receiver(post_delete, sender=IdeaDraft)
def delete_file(sender, instance, **kwargs):
    field = instance.pdf if sender is IdeaDraft else instance.idea_pdf
    if field:
        queue_deletion(field.name, private=sender is IdeaDraft)


@receiver(pre_save, sender=IdeaSubmission)
@receiver(pre_save, sender=IdeaDraft)
def replace_file(sender, instance, **kwargs):
    if not instance.pk:
        return
    field = "pdf" if sender is IdeaDraft else "idea_pdf"
    old = sender.objects.filter(pk=instance.pk).values_list(field, flat=True).first()
    if old and old != getattr(instance, field).name:
        queue_deletion(old, private=sender is IdeaDraft)
