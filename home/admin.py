from django.contrib import admin
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import IdeaSubmission
from .models import Collaborator, Comment, CommentReport
from .moderation_services import moderate_comment, dismiss_report

admin.site.site_header = "Administração Maflo Tech"
admin.site.site_title = "Maflo Tech"
admin.site.index_title = "Gerenciamento"


@admin.register(IdeaSubmission)
class IdeaSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "idea_title",
        "author_name",
        "status",
        "is_approved",
        "is_featured",
        "is_active",
        "created_at",
    )

    search_fields = (
        "idea_title",
        "author_name",
    )

    list_filter = (
        "status",
        "is_approved",
        "is_featured",
        "is_active",
        "created_at",
    )

    ordering = ("-created_at", "-pk")

    readonly_fields = (
        "owner",
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
                "owner",
                "idea_description",
                "idea_pdf",
                "idea_github",
            ),
        }),
        ("Publicação", {
            "fields": (
                "status",
                "is_approved",
                "is_featured",
                "is_active",
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

    def _moderate_selected(self, request, queryset, action):
        count = 0
        with transaction.atomic():
            for comment_id, idea_id in queryset.order_by("idea_id", "pk").values_list("pk", "idea_id"):
                try:
                    moderate_comment(
                        user=request.user, idea_id=idea_id,
                        comment_id=comment_id, action=action,
                    )
                except ValidationError:
                    continue
                count += 1
        return count

    @admin.action(description="Aprovar e publicar comentários selecionados", permissions=["change"])
    def approve_comments(self, request, queryset):
        count = self._moderate_selected(request, queryset, "approve")
        self.message_user(request, f"{count} comentário(s) aprovado(s). Comentários removidos pelo autor foram preservados.")

    @admin.action(description="Desativar comentários selecionados", permissions=["change"])
    def disable_comments(self, request, queryset):
        count = self._moderate_selected(request, queryset, "disable")
        self.message_user(request, f"{count} comentário(s) desativado(s). Comentários removidos pelo autor foram preservados.")


@admin.register(CommentReport)
class CommentReportAdmin(admin.ModelAdmin):
    def get_urls(self):
        from django.urls import path
        return [path("<int:report_id>/descartar/", self.admin_site.admin_view(self.dismiss_view), name="home_commentreport_dismiss")] + super().get_urls()

    def dismiss_view(self, request, report_id):
        from django import forms
        from django.shortcuts import get_object_or_404, redirect
        from django.template.response import TemplateResponse
        from .moderation_services import require_management_permission
        require_management_permission(request.user, "home.change_commentreport")
        class DismissForm(forms.Form):
            note = forms.CharField(label="Motivo do descarte", max_length=1000, widget=forms.Textarea)
        report = get_object_or_404(CommentReport, pk=report_id)
        form = DismissForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                dismiss_report(user=request.user, report_id=report_id, note=form.cleaned_data["note"])
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.message_user(request, "Denúncia descartada e avaliação registrada.")
                return redirect("admin:home_commentreport_changelist")
        return TemplateResponse(request, "admin/dismiss_report.html", {**self.admin_site.each_context(request), "title": "Descartar denúncia", "form": form, "report": report, "opts": self.model._meta})

    @admin.display(description="Avaliação")
    def resolution_link(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        if obj.reviewed_at:
            return "Descartada" if obj.dismissed else "Avaliada"
        return format_html('<a href="{}">Descartar com motivo</a>', reverse("admin:home_commentreport_dismiss", args=[obj.pk]))

    list_display = (
        "id",
        "comment",
        "reporter",
        "reason",
        "created_at",
        "reviewed_at",
        "resolution_link",
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
        "review_note",
        "dismissed",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

_original_each_context = admin.site.each_context

def organizer_context(request):
    context = _original_each_context(request)
    if not request.user.is_active or not request.user.is_staff:
        return context
    cards = []
    def add_card(model, label, queryset, query):
        opts = model._meta
        if request.user.has_perm(f"{opts.app_label}.view_{opts.model_name}") or request.user.has_perm(f"{opts.app_label}.change_{opts.model_name}"):
            from django.urls import reverse
            cards.append({"label": label, "count": queryset.count(),
                "url": reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist") + "?" + query})
    add_card(Comment, "Comentários aguardando aprovação", Comment.objects.filter(status="pending", removed_at__isnull=True), "status__exact=pending&removed_at__isnull=True")
    add_card(CommentReport, "Denúncias pendentes", CommentReport.objects.filter(reviewed_at__isnull=True), "reviewed_at__isnull=True")
    add_card(IdeaSubmission, "Ideias aguardando publicação", IdeaSubmission.objects.filter(is_approved=False, is_active=True), "is_approved__exact=0&is_active__exact=1")
    context["organizer_cards"] = cards
    return context

admin.site.each_context = organizer_context
admin.site.index_template = "admin/organizer_index.html"
