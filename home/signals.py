from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import IdeaSubmission


@receiver(post_delete, sender=IdeaSubmission)
def delete_idea_pdf(sender, instance, **kwargs):
    if instance.idea_pdf:
        storage, name = instance.idea_pdf.storage, instance.idea_pdf.name
        transaction.on_commit(lambda: storage.delete(name))
