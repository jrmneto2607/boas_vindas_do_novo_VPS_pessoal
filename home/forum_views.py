from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from .forms.forum import CommentForm, CommentReportForm
from .forum_services import create_comment, change_own_comment, report_comment, require_participant
from .models import IdeaSubmission, Comment
from .forum_html import sanitize_message
from django.db import transaction
from .views import idea_detail


@login_required
@require_POST
def comment_create(request, pk):
    get_object_or_404(IdeaSubmission, pk=pk, is_active=True, is_approved=True)
    form = CommentForm(request.POST)
    if form.is_valid():
        try:
            create_comment(
                user=request.user,
                idea_id=pk,
                cleaned_data=form.cleaned_data,
            )
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(request, "Sua contribuição foi enviada.")
            return redirect(f"{reverse('idea_detail', args=[pk])}#forum-form")
    return idea_detail(request, pk, comment_form=form, response_status=400)


@login_required
@require_http_methods(["GET", "POST"])
def comment_edit(request, pk, comment_id):
    get_object_or_404(IdeaSubmission, pk=pk, is_active=True, is_approved=True)
    with transaction.atomic():
        author = require_participant(request.user)
    comment = get_object_or_404(Comment, pk=comment_id, idea_id=pk, author=author, removed_at__isnull=True)
    form = CommentForm(request.POST if request.method == "POST" else None,
                       initial={"message": comment.message, "github_url": comment.github_url})
    form.fields.pop("parent_id")
    if request.method == "POST" and form.is_valid():
        change_own_comment(user=request.user, idea_id=pk, comment_id=comment_id, cleaned_data=form.cleaned_data)
        messages.success(request, "Sua contribuição foi atualizada.")
        return redirect(f"{reverse('idea_detail', args=[pk])}?comentario={comment_id}#comment-{comment_id}")
    return render(request, "home/forum_action.html", {"idea_id": pk, "form": form,
        "title": "Editar contribuição", "button_label": "Salvar alterações", "is_editor": True,
        "editor_initial": sanitize_message(form["message"].value() or "")})


@login_required
@require_POST
def comment_remove(request, pk, comment_id):
    change_own_comment(user=request.user, idea_id=pk, comment_id=comment_id)
    messages.success(request, "Sua contribuição foi removida.")
    return redirect(f"{reverse('idea_detail', args=[pk])}#forum")


@login_required
@require_http_methods(["GET", "POST"])
def comment_report(request, pk, comment_id):
    get_object_or_404(IdeaSubmission, pk=pk, is_active=True, is_approved=True)
    with transaction.atomic():
        author = require_participant(request.user)
    get_object_or_404(Comment.objects.exclude(author=author), pk=comment_id, idea_id=pk,
                      removed_at__isnull=True, status=Comment.Status.PUBLISHED)
    form = CommentReportForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            report_comment(user=request.user, idea_id=pk, comment_id=comment_id, cleaned_data=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Denúncia enviada à administração.")
            return redirect(f"{reverse('idea_detail', args=[pk])}#forum")
    return render(request, "home/forum_action.html", {"idea_id": pk, "form": form,
        "title": "Denunciar contribuição", "button_label": "Enviar denúncia"})
