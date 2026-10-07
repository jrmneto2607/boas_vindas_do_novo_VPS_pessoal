import base64
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms.ideas import IdeaSubmissionForm
from .forum_services import get_forum_access
from .models import IdeaSubmission

DRAFT_KEY = "idea_submission_draft"


def get_draft(request):
    draft = request.session.get(DRAFT_KEY)
    if draft and draft.get("expires", 0) > timezone.now().timestamp():
        return draft
    request.session.pop(DRAFT_KEY, None)
    return None


def draft_files(draft):
    if draft and draft.get("pdf"):
        return {"idea_pdf": SimpleUploadedFile(draft["pdf_name"], base64.b64decode(draft["pdf"]), content_type="application/pdf")}
    return {}


def submit_idea(request):
    draft = get_draft(request)
    decision = request.POST.get("submission_choice")
    if decision in ("login", "anonymous"):
        if not draft:
            messages.error(request, "O rascunho expirou. Preencha a ideia novamente.")
            return redirect(reverse("home") + "#enviar-ideia")
        data, files = draft["data"], draft_files(draft)
    else:
        data = request.POST
        files = request.FILES or (draft_files(draft) if not request.POST.get("discard_pdf") else {})
    form = IdeaSubmissionForm(data, files)
    if not form.is_valid():
        return form
    if request.user.is_authenticated and not get_forum_access(request.user)["can_participate"]:
        form.add_error(None, "Sua conta não está habilitada para enviar ideias.")
        return form
    if not request.user.is_authenticated and decision != "anonymous":
        cleaned = dict(form.cleaned_data)
        pdf = cleaned.pop("idea_pdf", None)
        request.session[DRAFT_KEY] = {"data": cleaned,
            "pdf": base64.b64encode(pdf.read()).decode() if pdf else "",
            "pdf_name": pdf.name if pdf else "",
            "expires": (timezone.now() + timedelta(hours=1)).timestamp()}
        if decision == "login":
            return redirect(reverse("login") + "?" + urlencode({"next": reverse("home") + "#enviar-ideia"}))
        return render(request, "home/idea_submission_choice.html")
    idea = IdeaSubmission.objects.create(**form.cleaned_data,
        owner=request.user if request.user.is_authenticated else None,
        consent_accepted_at=timezone.now())
    request.session.pop(DRAFT_KEY, None)
    messages.success(request, "Sua ideia foi enviada e vinculada à sua conta!" if idea.owner_id else "Sua ideia foi enviada com sucesso!")
    return redirect(reverse("home") + "#enviar-ideia")
