import uuid
from django.db import models
from django.conf import settings
from django.db.models import Q

def idea_pdf_upload_path(instance, filename):
    # Gera um nome de arquivo único usando UUID
    unique_filename = f"Idea_{uuid.uuid4().hex}.pdf"
    return f"ideas/pdfs/{unique_filename}"

# Create your models here.
class IdeaSubmission(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="submitted_ideas")
    author_name = models.CharField(max_length=100)
    idea_title = models.CharField(max_length=200)
    idea_description = models.TextField(blank=True, default="")

    idea_pdf = models.FileField(upload_to=idea_pdf_upload_path, blank=True, max_length=255)
    idea_github = models.URLField(max_length=500, blank=True)

    contact_email = models.EmailField(max_length=254, blank=True)
    contact_whatsapp = models.CharField(max_length=30, blank=True)

    idea_consent = models.BooleanField(default=False)

    # Campos usados para informações geradas automaticamente
    consent_version = models.CharField(max_length=20, default="1.0")
    consent_accepted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Status(models.IntegerChoices):
        EM_ANALISE = 1, 'Em análise'
        EM_DESENVOLVIMENTO = 2, 'Em desenvolvimento'
        CONCLUIDA = 3, 'Concluída'

    status = models.PositiveSmallIntegerField(
        choices=Status.choices,
        default=Status.EM_ANALISE,
    )

    is_approved = models.BooleanField("Publicação aprovada", default=False)

    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField("Ideia ativa", default=True)

# PREPARANDO A ÁREA DO FORUM DE CADA IDEIA

class Collaborator(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collaborator",
    )
    public_name = models.CharField("Nome ou pseudônimo", max_length=100)

    # Privados: não devem ser enviados aos templates públicos.
    email = models.EmailField("E-mail", unique=True)
    whatsapp = models.CharField(
        "WhatsApp",
        max_length=30,
        blank=True,
    )
    email_confirmed_at = models.DateTimeField(
        "E-mail confirmado em",
        null=True,
        blank=True,
    )

    class ContactPreference(models.TextChoices):
        NONE = "none", "Não desejo contato"
        EMAIL = "email", "E-mail"
        WHATSAPP = "whatsapp", "WhatsApp"

    contact_preference = models.CharField(
        "Preferência de contato",
        max_length=10,
        choices=ContactPreference.choices,
        default=ContactPreference.NONE,
    )
    contact_authorized = models.BooleanField(
        "Autoriza contato sobre contribuições",
        default=False,
    )
    contact_consent_at = models.DateTimeField(
        "Autorização de contato registrada em",
        null=True,
        blank=True,
    )
    consent_version = models.CharField(max_length=20, default="1.0")

    can_publish_directly = models.BooleanField(
        "Pode publicar sem aprovação",
        default=False,
    )

    confirmation_sent_at = models.DateTimeField(
        "Última confirmação enviada em",
        null=True,
        blank=True,
    )
    is_blocked = models.BooleanField("Participação bloqueada", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Colaborador"
        verbose_name_plural = "Colaboradores"

    def __str__(self):
        return self.public_name


class Comment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Aguardando aprovação"
        PUBLISHED = "published", "Publicado"
        REPORTED = "reported", "Oculto por denúncias"
        DISABLED = "disabled", "Desativado pela administração"

    idea = models.ForeignKey(
        IdeaSubmission,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Ideia",
    )
    author = models.ForeignKey(
        Collaborator,
        on_delete=models.PROTECT,
        related_name="comments",
        verbose_name="Autor",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="replies",
        null=True,
        blank=True,
        verbose_name="Comentário respondido",
    )

    message = models.TextField("Mensagem", max_length=10000)
    github_url = models.URLField("GitHub", max_length=500, blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Remoção pelo autor é separada da decisão de moderação.
    removed_at = models.DateTimeField(
        "Removido pelo autor em",
        null=True,
        blank=True,
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="moderated_comments",
        null=True,
        blank=True,
        verbose_name="Moderado por",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_note = models.TextField(
        "Observação interna",
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comentário"
        verbose_name_plural = "Comentários"
        ordering = ("created_at", "pk")
        indexes = [
            models.Index(fields=["idea", "status", "created_at"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError(
                    {"parent": "Um comentário não pode responder a si mesmo."}
                )

            if self.parent.idea_id != self.idea_id:
                raise ValidationError(
                    {"parent": "A resposta deve pertencer à mesma ideia."}
                )

            # Uma camada de respostas mantém a conversa organizada.
            if self.parent.parent_id:
                raise ValidationError(
                    {"parent": "Responda ao comentário principal da conversa."}
                )

    def __str__(self):
        return f"Comentário #{self.pk} — {self.author.public_name}"


class CommentReport(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam ou publicidade"
        ABUSE = "abuse", "Ofensa ou assédio"
        UNSAFE = "unsafe", "Conteúdo ou link perigoso"
        OTHER = "other", "Outro motivo"

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name="Comentário",
    )
    reporter = models.ForeignKey(
        Collaborator,
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="Denunciante",
    )
    reason = models.CharField(
        "Motivo",
        max_length=10,
        choices=Reason.choices,
    )
    details = models.TextField(
        "Detalhes",
        max_length=1000,
        blank=True,
    )

    review_note = models.TextField("Motivo da avaliação", blank=True, max_length=1000)
    dismissed = models.BooleanField("Denúncia descartada", default=False)

    reviewed_at = models.DateTimeField(
        "Avaliada em",
        null=True,
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_comment_reports",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Denúncia"
        verbose_name_plural = "Denúncias"
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "reporter"],
                name="unique_report_per_comment_and_user",
            ),
        ]
        indexes = [
            models.Index(
                fields=["comment"],
                condition=Q(reviewed_at__isnull=True),
                name="pending_comment_reports",
            ),
        ]

    def __str__(self):
        return f"Denúncia do comentário #{self.comment_id}"