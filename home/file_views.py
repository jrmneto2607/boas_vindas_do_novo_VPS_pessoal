from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from .models import IdeaSubmission
from .moderation_services import can_manage


@require_safe
def idea_pdf(request, pk=None, path=None):
    idea = get_object_or_404(IdeaSubmission, **({"pk": pk} if pk is not None else {"idea_pdf": path}))
    public = idea.is_active and idea.is_approved
    owner = request.user.is_authenticated and idea.owner_id == request.user.pk
    staff = can_manage(request.user, "home.view_ideasubmission") or can_manage(request.user, "home.change_ideasubmission")
    if not public and not owner and not staff:
        raise Http404()
    if not idea.idea_pdf:
        raise Http404()
    try:
        response = FileResponse(idea.idea_pdf.open("rb"), as_attachment=True, filename="ideia.pdf", content_type="application/pdf")
    except FileNotFoundError:
        raise Http404() from None
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
