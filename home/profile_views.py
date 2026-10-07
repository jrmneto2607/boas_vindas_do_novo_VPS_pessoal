from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

import html
from django.utils.html import strip_tags
from .forum_html import sanitize_message
from .forms.profile import ProfileForm
from .models import Collaborator, Comment, IdeaSubmission


@login_required
def profile(request):
    collaborator = get_object_or_404(Collaborator, user=request.user)
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=collaborator)
    if request.method == "POST" and form.is_valid():
        changed = any(key in form.changed_data for key in ("contact_preference", "contact_authorized", "whatsapp"))
        collaborator = form.save(commit=False)
        if changed:
            collaborator.contact_consent_at = timezone.now() if collaborator.contact_authorized else None
        collaborator.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("profile")
    ideas = IdeaSubmission.objects.filter(owner=request.user).annotate(
        has_comments=Exists(Comment.objects.filter(idea_id=OuterRef("pk")))
    ).order_by("-created_at", "-pk")
    idea_page = Paginator(ideas, 10).get_page(request.GET.get("ideias"))
    for idea in idea_page:
        idea.can_remove = idea.status == IdeaSubmission.Status.EM_ANALISE and not idea.has_comments and not collaborator.is_blocked
    contributions = Comment.objects.filter(author=collaborator).select_related("idea").order_by("-created_at", "-pk")
    contribution_page = Paginator(contributions, 10).get_page(request.GET.get("contribuicoes"))
    for contribution in contribution_page:
        contribution.excerpt = "" if contribution.removed_at else html.unescape(strip_tags(sanitize_message(contribution.message)))
    return render(request, "home/profile.html", {"form": form, "idea_page": idea_page,
        "contribution_page": contribution_page})


@login_required
@require_POST
@transaction.atomic
def idea_remove(request, pk):
    collaborator = get_object_or_404(Collaborator.objects.select_for_update(), user=request.user)
    if collaborator.is_blocked or not request.user.is_active or not collaborator.email_confirmed_at:
        raise PermissionDenied("Sua conta não está habilitada para esta ação.")
    idea = get_object_or_404(IdeaSubmission.objects.select_for_update(), pk=pk, owner=request.user)
    if idea.status != IdeaSubmission.Status.EM_ANALISE or idea.comments.exists():
        messages.error(request, "Só é possível excluir uma ideia em análise que nunca recebeu comentários.")
        return redirect("profile")
    idea.delete()
    messages.success(request, "Ideia excluída.")
    return redirect("profile")
