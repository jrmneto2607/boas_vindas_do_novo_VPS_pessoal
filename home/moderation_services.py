from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Collaborator, Comment, CommentReport, IdeaSubmission


def can_manage(user, permission):
    if not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or (user.is_staff and user.has_perm(permission))


def require_management_permission(user, permission):
    if not can_manage(user, permission):
        raise PermissionDenied("Você não tem permissão para realizar esta ação.")


@transaction.atomic
def moderate_comment(*, user, idea_id, comment_id, action):
    require_management_permission(user, "home.change_comment")
    statuses = {
        "approve": Comment.Status.PUBLISHED,
        "disable": Comment.Status.DISABLED,
    }
    if action not in statuses:
        raise ValidationError("Ação de moderação inválida.")

    # Bloquear autor antes da ideia e do comentário, como no envio.
    target = get_object_or_404(Comment, pk=comment_id, idea_id=idea_id)
    author = Collaborator.objects.select_for_update().get(pk=target.author_id)
    get_object_or_404(IdeaSubmission.objects.select_for_update(), pk=idea_id)
    comment = get_object_or_404(
        Comment.objects.select_for_update(), pk=comment_id, idea_id=idea_id,
    )
    if comment.removed_at is not None:
        raise ValidationError("Esse comentário foi removido pelo autor.")
    comment.status = statuses[action]
    comment.moderated_by = user
    comment.moderated_at = timezone.now()
    comment.save(update_fields=["status", "moderated_by", "moderated_at"])
    if action == "approve" and not author.can_publish_directly:
        author.can_publish_directly = True
        author.save(update_fields=["can_publish_directly"])
        LogEntry.objects.log_actions(
            user_id=user.pk, queryset=[author], action_flag=CHANGE,
            change_message="Publicação direta liberada após aprovação de comentário.",
        )
    comment.reports.filter(reviewed_at__isnull=True).update(
        reviewed_at=comment.moderated_at, reviewed_by=user,
    )
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[comment], action_flag=CHANGE,
        change_message=("Comentário aprovado." if action == "approve" else "Comentário desativado."),
    )
    return comment


@transaction.atomic
def deactivate_idea(*, user, idea_id):
    require_management_permission(user, "home.change_ideasubmission")
    idea = get_object_or_404(IdeaSubmission.objects.select_for_update(), pk=idea_id)
    if idea.is_active:
        idea.is_active = False
        idea.save(update_fields=["is_active"])
        LogEntry.objects.log_actions(
            user_id=user.pk, queryset=[idea], action_flag=CHANGE,
            change_message="Ideia desativada pelo site.",
        )
    return idea


@transaction.atomic
def dismiss_report(*, user, report_id, note):
    require_management_permission(user, "home.change_commentreport")
    note = note.strip()
    if not note or len(note) > 1000:
        raise ValidationError("Informe um motivo de até 1000 caracteres.")
    target = get_object_or_404(CommentReport.objects.select_related("comment"), pk=report_id)
    # Mesma ordem de bloqueio usada nas contribuições e na moderação.
    Collaborator.objects.select_for_update().get(pk=target.comment.author_id)
    IdeaSubmission.objects.select_for_update().get(pk=target.comment.idea_id)
    comment = Comment.objects.select_for_update().get(pk=target.comment_id)
    report = CommentReport.objects.select_for_update().get(pk=report_id)
    if report.reviewed_at:
        raise ValidationError("Esta denúncia já foi avaliada.")
    report.reviewed_at = timezone.now()
    report.reviewed_by = user
    report.review_note = note
    report.dismissed = True
    report.save(update_fields=["reviewed_at", "reviewed_by", "review_note", "dismissed"])
    if comment.status == Comment.Status.REPORTED and comment.reports.filter(reviewed_at__isnull=True).count() < 2:
        comment.status = Comment.Status.PUBLISHED
        comment.save(update_fields=["status"])
    LogEntry.objects.log_actions(user_id=user.pk, queryset=[report], action_flag=CHANGE, change_message="Denúncia descartada: " + note)
    return report
