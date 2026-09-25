import uuid
from django.db import models

def idea_pdf_upload_path(instance, filename):
    # Gera um nome de arquivo único usando UUID
    unique_filename = f"Idea_{uuid.uuid4().hex}.pdf"
    return f"ideas/pdfs/{unique_filename}"

# Create your models here.
class IdeaSubmission(models.Model):
    author_name = models.CharField(max_length=100)
    idea_title = models.CharField(max_length=200)

    idea_pdf = models.FileField(upload_to=idea_pdf_upload_path, blank=True, max_length=255)
    idea_github = models.URLField(max_length=500, blank=True)

    contact_email = models.EmailField(max_length=254, blank=True)
    contact_whatsapp = models.CharField(max_length=30, blank=True)

    idea_consent = models.BooleanField(default=False)

    # Campos usados para informações geradas automaticamente
    consent_version = models.CharField(max_length=20, default="1.0")
    consent_accepted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)