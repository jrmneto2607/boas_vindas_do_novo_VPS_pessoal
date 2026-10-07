import uuid
from datetime import timedelta
from urllib.parse import urlencode
from django.contrib import messages
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from .forms.ideas import IdeaSubmissionForm
from .forum_services import get_forum_access
from .models import IdeaSubmission, IdeaDraft, SubmissionReceipt

DRAFT_KEY = "idea_submission_draft"
TOKEN_SALT = "home.idea-submission.v1"


def submission_key(request):
    key = request.session.get("idea_submission_key")
    if not key:
        key = str(uuid.uuid4())
        request.session["idea_submission_key"] = key
    return signing.dumps(key, salt=TOKEN_SALT)


def get_draft(request):
    stub = request.session.get(DRAFT_KEY)
    if not stub:
        return None
    if "id" not in stub:
        if stub.get("expires", 0) <= timezone.now().timestamp():
            request.session.pop(DRAFT_KEY, None)
            return None
        import base64
        from datetime import datetime, timezone as utc
        pdf = SimpleUploadedFile(stub.get("pdf_name", "proposta.pdf"), base64.b64decode(stub["pdf"])) if stub.get("pdf") else None
        record = IdeaDraft.objects.create(data=stub["data"], pdf=pdf or "", pdf_name=stub.get("pdf_name", ""), expires_at=datetime.fromtimestamp(stub["expires"], tz=utc.utc))
        stub = {"id": str(record.pk), "expires": stub["expires"]}
        request.session[DRAFT_KEY] = stub
    draft = IdeaDraft.objects.filter(pk=stub["id"]).first()
    if not draft or draft.expires_at <= timezone.now() or stub.get("expires", 0) <= timezone.now().timestamp():
        if draft:
            draft.delete()
        request.session.pop(DRAFT_KEY, None)
        return None
    return {"id": str(draft.pk), "data": draft.data, "pdf_name": draft.pdf_name, "expires": draft.expires_at.timestamp()}


def extend_draft(request, hours=24):
    draft = get_draft(request)
    if draft:
        expiry = timezone.now() + timedelta(hours=hours)
        IdeaDraft.objects.filter(pk=draft["id"]).update(expires_at=expiry)
        request.session[DRAFT_KEY] = {"id": draft["id"], "expires": expiry.timestamp()}


def draft_files(draft):
    if draft:
        record = IdeaDraft.objects.filter(pk=draft["id"]).first()
        if record and record.pdf:
            with record.pdf.open("rb") as source:
                return {"idea_pdf": SimpleUploadedFile(record.pdf_name, source.read(), content_type="application/pdf")}
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
        record = IdeaDraft.objects.create(data=cleaned, pdf=pdf or "", pdf_name=pdf.name if pdf else "", expires_at=timezone.now() + timedelta(hours=1))
        request.session[DRAFT_KEY] = {"id": str(record.pk), "expires": record.expires_at.timestamp()}
        submission_key(request)
        if draft:
            IdeaDraft.objects.filter(pk=draft["id"]).delete()
        if decision == "login":
            return redirect(reverse("login") + "?" + urlencode({"next": reverse("home") + "#enviar-ideia"}))
        return render(request, "home/idea_submission_choice.html")
    token = request.POST.get("submission_key") or submission_key(request)
    try:
        key = str(uuid.UUID(signing.loads(token, salt=TOKEN_SALT, max_age=86400)))
    except (signing.BadSignature, ValueError, TypeError):
        form.add_error(None, "Recarregue o formulário para enviar a ideia.")
        return form
    with transaction.atomic():
        SubmissionReceipt.objects.get_or_create(pk=key)
        receipt = SubmissionReceipt.objects.select_for_update().get(pk=key)
        if not receipt.completed:
            receipt.idea = IdeaSubmission.objects.create(**form.cleaned_data,
                owner=request.user if request.user.is_authenticated else None,
                consent_accepted_at=timezone.now())
            receipt.completed = True
            receipt.save(update_fields=["idea", "completed"])
        idea = receipt.idea
    if draft:
        IdeaDraft.objects.filter(pk=draft["id"]).delete()
    request.session.pop(DRAFT_KEY, None)
    request.session.pop("idea_submission_key", None)
    messages.success(request, "Sua ideia foi enviada e vinculada à sua conta!" if idea and idea.owner_id else "Sua ideia foi enviada com sucesso!")
    return redirect(reverse("home") + "#enviar-ideia")
