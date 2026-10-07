from django.core.management.base import BaseCommand
from django.utils import timezone
from home.models import IdeaDraft, PendingFileDeletion, RequestBucket
from home.signals import attempt_deletion


class Command(BaseCommand):
    help = "Remove rascunhos expirados e repete exclusões de arquivos pendentes."

    def handle(self, *args, **options):
        IdeaDraft.objects.filter(expires_at__lte=timezone.now()).delete()
        RequestBucket.objects.filter(expires_at__lte=timezone.now()).delete()
        for job in PendingFileDeletion.objects.iterator():
            attempt_deletion(job)
        self.stdout.write(self.style.SUCCESS("Limpeza concluída."))
