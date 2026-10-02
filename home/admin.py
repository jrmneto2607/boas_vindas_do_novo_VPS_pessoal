from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from .models import IdeaSubmission
from .models import Collaborator, Comment, CommentReport

admin.site.site_header = "Administração Maflo Tech"
admin.site.site_title = "Maflo Tech"
admin.site.index_title = "Gerenciamento"


@admin.register(IdeaSubmission)
class IdeaSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "idea_title",
        "author_name",
        "status",
        "is_featured",
        "created_at",
    )

    search_fields = (
        "idea_title",
        "author_name",
    )

    list_filter = (
        "status",
        "is_featured",
        "created_at",
    )

    ordering = ("-created_at", "-pk")

    readonly_fields = (
        "created_at",
        "idea_consent",
        "consent_version",
        "consent_accepted_at",
    )

    fieldsets = (
        ("Ideia", {
            "fields": (
                "idea_title",
                "author_name",
                "idea_description",
                "idea_pdf",
                "idea_github",
            ),
        }),
        ("Publicação", {
            "fields": (
                "status",
                "is_featured",
            ),
        }),
        ("Contato", {
            "fields": (
                "contact_email",
                "contact_whatsapp",
            ),
        }),
        ("Consentimento e registro", {
            "fields": (
                "idea_consent",
                "consent_version",
                "consent_accepted_at",
                "created_at",
            ),
        }),
    )


# Área de administração do fórum de ideias

@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    list_display = (
        "public_name",
        "email",
        "email_confirmed_at",
        "can_publish_directly",
        "is_blocked",
    )
    search_fields = ("public_name", "email")
    list_filter = (
        "is_blocked",
        "can_publish_directly",
        "contact_preference",
    )

    readonly_fields = (
        "user",
        "public_name",
        "email",
        "whatsapp",
        "email_confirmed_at",
        "contact_preference",
        "contact_authorized",
        "contact_consent_at",
        "consent_version",
        "created_at",
    )

    fieldsets = (
        ("Conta", {
            "fields": (
                "user",
                "public_name",
                "email",
                "email_confirmed_at",
                "created_at",
            ),
        }),
        ("Participação", {
            "fields": (
                "can_publish_directly",
                "is_blocked",
            ),
        }),
        ("Contato privado e autorização", {
            "fields": (
                "whatsapp",
                "contact_preference",
                "contact_authorized",
                "contact_consent_at",
                "consent_version",
            ),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "idea",
        "author",
        "status",
        "removed_at",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "idea__idea_title",
        "author__public_name",
        "message",
    )
    list_select_related = ("idea", "author")
    ordering = ("-created_at", "-pk")

    readonly_fields = (
        "idea",
        "author",
        "parent",
        "message",
        "github_url",
        "status",
        "removed_at",
        "moderated_by",
        "moderated_at",
        "created_at",
    )
    fields = readonly_fields + ("moderation_note",)

    actions = ("approve_comments", "disable_comments")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(
        description="Aprovar e publicar comentários selecionados",
        permissions=["change"],
    )
    def approve_comments(self, request, queryset):
        approved = 0

        with transaction.atomic():
            comments = (
                queryset
                .select_for_update()
                .order_by("pk")
            )

            for comment in comments:
                # A administração não republica conteúdo removido pelo autor.
                if comment.removed_at is not None:
                    continue

                comment.status = Comment.Status.PUBLISHED
                comment.moderated_by = request.user
                comment.moderated_at = timezone.now()
                comment.save(update_fields=[
                    "status",
                    "moderated_by",
                    "moderated_at",
                ])

                # As denúncias anteriores foram avaliadas nesta decisão.
                comment.reports.filter(
                    reviewed_at__isnull=True,
                ).update(
                    reviewed_at=comment.moderated_at,
                    reviewed_by=request.user,
                )

                approved += 1

        self.message_user(
            request,
            f"{approved} comentário(s) aprovado(s). "
            "Comentários removidos pelo autor foram preservados.",
        )

    @admin.action(
        description="Desativar comentários selecionados",
        permissions=["change"],
    )
    def disable_comments(self, request, queryset):
        disabled = 0

        with transaction.atomic():
            comments = (
                queryset
                .select_for_update()
                .order_by("pk")
            )

            for comment in comments:
                comment.status = Comment.Status.DISABLED
                comment.moderated_by = request.user
                comment.moderated_at = timezone.now()
                comment.save(update_fields=[
                    "status",
                    "moderated_by",
                    "moderated_at",
                ])

                comment.reports.filter(
                    reviewed_at__isnull=True,
                ).update(
                    reviewed_at=comment.moderated_at,
                    reviewed_by=request.user,
                )

                disabled += 1

        self.message_user(
            request,
            f"{disabled} comentário(s) desativado(s).",
        )


@admin.register(CommentReport)
class CommentReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "comment",
        "reporter",
        "reason",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("reason", "reviewed_at")
    search_fields = (
        "comment__idea__idea_title",
        "reporter__public_name",
        "details",
    )
    list_select_related = ("comment", "reporter")
    ordering = ("-created_at", "-pk")

    readonly_fields = (
        "comment",
        "reporter",
        "reason",
        "details",
        "created_at",
        "reviewed_at",
        "reviewed_by",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False