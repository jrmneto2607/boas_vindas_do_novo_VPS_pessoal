from datetime import timedelta
from urllib.parse import urlsplit

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from .forum_html import sanitize_message
from .models import Collaborator, Comment, CommentReport, IdeaSubmission
from .moderation_services import can_manage


def participation_error(user, collaborator):
    """Retorna o impedimento para participar, ou uma string vazia."""
    if not user.is_authenticated:
        return "Entre na sua conta para participar da discussão."
    if not user.is_active:
        return "Sua conta está desativada."
    if collaborator is None:
        return "Sua conta não possui um cadastro de colaborador."
    if collaborator.is_blocked:
        return "Sua participação está bloqueada."
    if collaborator.email_confirmed_at is None:
        return "Confirme seu e-mail para participar da discussão."
    return ""


def get_forum_access(user):
    """Obtém os dados de acesso usados na apresentação da página."""
    collaborator = None
    if user.is_authenticated:
        collaborator = Collaborator.objects.filter(user_id=user.pk).first()

    error = participation_error(user, collaborator)
    return {
        "can_participate": not bool(error),
        "participation_message": error,
    }


def require_participant(user):
    """Exige uma conta habilitada; chamar dentro de transaction.atomic()."""
    collaborator = None
    if user.is_authenticated:
        collaborator = (
            Collaborator.objects
            .select_for_update()
            .filter(user_id=user.pk)
            .first()
        )

    error = participation_error(user, collaborator)
    if error:
        raise PermissionDenied(error)
    return collaborator

def replyable_comments(*, idea_id, author_id=None):
    """Comentários públicos ou contribuições do próprio autor em análise."""
    allowed = Q(status=Comment.Status.PUBLISHED)
    if author_id is not None:
        allowed |= Q(
            author_id=author_id,
            status__in=[Comment.Status.PENDING, Comment.Status.REPORTED],
        )
    return Comment.objects.filter(
        allowed, idea_id=idea_id, parent__isnull=True, removed_at__isnull=True,
    )


@transaction.atomic
def create_comment(*, user, idea_id, cleaned_data):
    """Salva uma contribuição usando dados de um CommentForm válido."""
    author = require_participant(user)
    if not author.user.is_active:
        raise PermissionDenied("Sua conta está desativada.")

    idea = IdeaSubmission.objects.select_for_update().get(pk=idea_id)
    if not idea.is_active:
        raise PermissionDenied("Essa ideia não está disponível para contribuições.")
    now = timezone.now()
    recent_comments = Comment.objects.filter(author=author)
    if recent_comments.filter(
        created_at__gte=now - timedelta(seconds=30),
    ).exists():
        raise ValidationError(
            "Aguarde 30 segundos entre suas contribuições."
        )
    if recent_comments.filter(
        created_at__gte=now - timedelta(hours=1),
    ).count() >= 20:
        raise ValidationError(
            "Você atingiu o limite de 20 contribuições por hora."
        )

    parent = None
    parent_id = cleaned_data.get("parent_id")
    if parent_id:
        parent = (
            replyable_comments(idea_id=idea.pk, author_id=author.pk)
            .select_for_update()
            .filter(pk=parent_id)
            .first()
        )
        if parent is None:
            raise ValidationError(
                "Esse comentário não está disponível para receber respostas."
            )

    comment = Comment(
        idea=idea,
        author=author,
        parent=parent,
        message=cleaned_data["message"],
        github_url=cleaned_data["github_url"],
        status=(
            Comment.Status.PUBLISHED
            if author.can_publish_directly and (
                parent is None or parent.status == Comment.Status.PUBLISHED
            )
            else Comment.Status.PENDING
        ),
    )
    comment.full_clean()
    comment.save()
    return comment

def prepare_forum_comment(comment, *, viewer_author_id=None, can_moderate=False):
    """Entrega somente dados de apresentação e HTML sanitizado."""
    removed = comment.removed_at is not None
    github_url = ""
    if not removed and comment.github_url:
        try:
            parsed = urlsplit(comment.github_url)
            if (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
            ):
                github_url = comment.github_url
        except ValueError:
            pass
    return {
        "id": comment.pk,
        "author_id": comment.author_id,
        "status": comment.status,
        "public_name": "" if removed else comment.author.public_name,
        "created_at": comment.created_at,
        "removed": removed,
        "message_html": "" if removed else sanitize_message(comment.message),
        "github_url": github_url,
        "status_label": (
            comment.get_status_display() if can_moderate and not removed
            else "Sua contribuição não foi aprovada."
            if not removed and comment.status == Comment.Status.DISABLED
            else ""
        ),
        "can_approve": can_moderate and not removed and comment.status != Comment.Status.PUBLISHED,
        "can_disable": can_moderate and not removed and comment.status != Comment.Status.DISABLED,
        "can_reply": (
            not removed
            and comment.parent_id is None
            and (
                comment.status == Comment.Status.PUBLISHED
                or (
                    comment.author_id == viewer_author_id
                    and comment.status in [Comment.Status.PENDING, Comment.Status.REPORTED]
                )
            )
        ),
    }


def get_forum_page(*, idea_id, user, page_number, order="recentes", target_comment_id=None):
    """Pagina conversas aplicando a visibilidade antes de renderizar."""
    author_id = None
    if user.is_authenticated:
        author_id = (
            Collaborator.objects.filter(user_id=user.pk)
            .values_list("pk", flat=True).first()
        )
    can_moderate = can_manage(user, "home.change_comment")
    visible = Q() if can_moderate else Q(status=Comment.Status.PUBLISHED)
    if author_id is not None and not can_moderate:
        visible |= Q(
            author_id=author_id,
            status__in=[
                Comment.Status.PENDING, Comment.Status.REPORTED, Comment.Status.DISABLED,
            ],
        )
    visible_replies = (
        Comment.objects.filter(
            visible, idea_id=idea_id, parent__isnull=False,
            removed_at__isnull=True,
        )
        .select_related("author")
        .order_by("created_at", "pk")
    )
    roots = (
        Comment.objects.filter(idea_id=idea_id, parent__isnull=True)
        .annotate(has_visible_replies=Exists(
            visible_replies.filter(parent_id=OuterRef("pk"))
        ))
        .filter(
            (visible & Q(removed_at__isnull=True))
            | (
                Q(removed_at__isnull=False, has_visible_replies=True)
                & ~Q(status=Comment.Status.DISABLED)
            )
        )
        .select_related("author")
        .order_by(*(("created_at", "pk") if order == "antigos" else ("-created_at", "-pk")))
    )
    if target_comment_id:
        target_root_id = roots.filter(pk=target_comment_id).values_list("pk", flat=True).first()
        if target_root_id is None:
            target_root_id = visible_replies.filter(pk=target_comment_id).values_list("parent_id", flat=True).first()
        if target_root_id:
            root_ids = list(roots.values_list("pk", flat=True))
            if target_root_id in root_ids:
                page_number = root_ids.index(target_root_id) // 10 + 1
    page = Paginator(roots, 10).get_page(page_number)
    root_comments = list(page.object_list)
    replies_by_parent = {}
    for reply in visible_replies.filter(
        parent_id__in=[comment.pk for comment in root_comments]
    ):
        replies_by_parent.setdefault(reply.parent_id, []).append(
            prepare_forum_comment(reply, viewer_author_id=author_id, can_moderate=can_moderate)
        )
    conversations = []
    for comment in root_comments:
        conversation = prepare_forum_comment(comment, viewer_author_id=author_id, can_moderate=can_moderate)
        conversation["replies"] = replies_by_parent.get(comment.pk, [])
        conversations.append(conversation)
    displayed_ids = [comment["id"] for comment in conversations]
    displayed_ids.extend(
        reply["id"] for comment in conversations for reply in comment["replies"]
    )
    page.has_other_rejected_contributions = (
        author_id is not None
        and Comment.objects.filter(
            idea_id=idea_id, author_id=author_id,
            status=Comment.Status.DISABLED, removed_at__isnull=True,
        ).exclude(pk__in=displayed_ids).exists()
    )
    page.contribution_count = roots.filter(removed_at__isnull=True).count() + visible_replies.filter(parent_id__in=roots.values("pk")).count()
    can_participate = get_forum_access(user)["can_participate"]
    page.order = "antigos" if order == "antigos" else "recentes"
    for item in conversations:
        for entry in [item, *item["replies"]]:
            entry["can_edit"] = entry["can_remove"] = bool(author_id and entry.get("author_id") == author_id and not entry["removed"] and can_participate)
            entry["can_report"] = bool(author_id and entry.get("author_id") != author_id and not entry["removed"] and entry.get("status") == Comment.Status.PUBLISHED and can_participate)
    page.object_list = conversations
    return page


@transaction.atomic
def change_own_comment(*, user, idea_id, comment_id, cleaned_data=None):
    author = require_participant(user)
    get_object_or_404_active_idea(idea_id)
    from django.shortcuts import get_object_or_404
    comment = get_object_or_404(Comment.objects.select_for_update(), pk=comment_id,
                               idea_id=idea_id, author=author, removed_at__isnull=True)
    if cleaned_data is None:
        comment.removed_at = timezone.now()
        comment.save(update_fields=["removed_at"])
    else:
        comment.message = cleaned_data["message"]
        comment.github_url = cleaned_data["github_url"]
        # Uma edição não contorna uma rejeição ou denúncia anterior.
        if comment.status in [Comment.Status.DISABLED, Comment.Status.REPORTED] or not author.can_publish_directly:
            comment.status = Comment.Status.PENDING
        comment.moderated_by = None
        comment.moderated_at = None
        comment.full_clean()
        comment.save(update_fields=["message", "github_url", "status", "moderated_by", "moderated_at"])
    return comment


def get_object_or_404_active_idea(idea_id):
    from django.shortcuts import get_object_or_404
    return get_object_or_404(IdeaSubmission.objects.select_for_update(), pk=idea_id, is_active=True)


@transaction.atomic
def report_comment(*, user, idea_id, comment_id, cleaned_data):
    author = require_participant(user)
    get_object_or_404_active_idea(idea_id)
    from django.shortcuts import get_object_or_404
    comment = get_object_or_404(Comment.objects.select_for_update(), pk=comment_id,
                               idea_id=idea_id, removed_at__isnull=True,
                               status=Comment.Status.PUBLISHED)
    if comment.author_id == author.pk:
        raise ValidationError("Você não pode denunciar sua própria contribuição.")
    if CommentReport.objects.filter(comment=comment, reporter=author).exists():
        raise ValidationError("Você já denunciou esta contribuição.")
    report = CommentReport(comment=comment, reporter=author, **cleaned_data)
    report.full_clean()
    report.save()
    if comment.reports.filter(reviewed_at__isnull=True).count() >= 2:
        comment.status = Comment.Status.REPORTED
        comment.save(update_fields=["status"])
    return report
