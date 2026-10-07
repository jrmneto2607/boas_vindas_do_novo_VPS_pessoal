from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import IdeaSubmission
from .moderation_services import deactivate_idea, moderate_comment


@require_POST
def comment_moderate(request, pk, comment_id):
    try:
        moderate_comment(
            user=request.user, idea_id=pk, comment_id=comment_id,
            action=request.POST.get("action"),
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Moderação registrada.")
    if not IdeaSubmission.objects.filter(pk=pk, is_active=True).exists():
        return redirect("admin:home_comment_changelist")
    return redirect(f"{reverse('idea_detail', args=[pk])}#forum")


@require_POST
def idea_deactivate(request, pk):
    deactivate_idea(user=request.user, idea_id=pk)
    messages.success(request, "A ideia foi desativada.")
    return redirect("idea_list")
