from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import Http404
from django.utils.html import strip_tags
import html
from .forms.ideas import IdeaSubmissionForm
from .forms.forum import CommentForm
from .forum_services import get_forum_access, get_forum_page, replyable_comments
from .forum_html import sanitize_message
from .models import Collaborator, IdeaSubmission
from .moderation_services import can_manage



# Create your views here.
def index(request):
    from .idea_submission import submit_idea, get_draft
    draft = get_draft(request)
    if request.method == "POST":
        result = submit_idea(request)
        if not isinstance(result, IdeaSubmissionForm):
            return result
        form = result
    else:
        form = IdeaSubmissionForm(initial=draft["data"] if draft else None)

    # Obter todas as ideias enviadas, ordenadas por data de criação (mais recentes primeiro)
    ideas = IdeaSubmission.objects.filter(is_active=True).order_by('-created_at', '-pk')
    # Obter ideias em destaque, limitando a 6 ideias aleatórias
    featured_ideas = IdeaSubmission.objects.filter(is_featured=True, is_active=True).order_by('?')[:6]

    return render(
        request, 
        'home/index.html',
        {
            'form': form,
            'saved_pdf_name': draft.get('pdf_name', '') if draft else '',
            'ideas': ideas,
            'featured_ideas': featured_ideas,
        }
    )


# AREA DE IDEIAS

PUBLIC_IDEA_FIELDS = (
    "id",
    "idea_title",
    "idea_description",
    "author_name",
    "status",
    "idea_pdf",
    "idea_github",
    "created_at",
)


def public_ideas():
    return IdeaSubmission.objects.filter(is_active=True).values(*PUBLIC_IDEA_FIELDS)


def prepare_public_idea(idea):
    idea["status_label"] = dict(
        IdeaSubmission.Status.choices
    ).get(idea["status"], "")

    pdf_storage = IdeaSubmission._meta.get_field("idea_pdf").storage
    idea["pdf_url"] = (
        pdf_storage.url(idea["idea_pdf"])
        if idea["idea_pdf"]
        else ""
    )

    return idea


def idea_list(request):
    title = request.GET.get("titulo", "").strip()
    status = request.GET.get("status", "")
    has_pdf = request.GET.get("pdf") == "1"
    has_github = request.GET.get("github") == "1"

    ideas = public_ideas().order_by("-created_at", "-id")

    if title:
        ideas = ideas.filter(idea_title__icontains=title)

    valid_statuses = {
        str(value) for value, label in IdeaSubmission.Status.choices
    }

    if status in valid_statuses:
        ideas = ideas.filter(status=int(status))
    else:
        status = ""

    if has_pdf:
        ideas = ideas.exclude(idea_pdf="")

    if has_github:
        ideas = ideas.exclude(idea_github="")

    page = Paginator(ideas, 12).get_page(request.GET.get("page"))
    page.object_list = [
        prepare_public_idea(idea) for idea in page.object_list
    ]

    query = request.GET.copy()
    query.pop("page", None)

    return render(request, "home/idea_list.html", {
        "page": page,
        "statuses": IdeaSubmission.Status.choices,
        "title_filter": title,
        "status_filter": status,
        "has_pdf": has_pdf,
        "has_github": has_github,
        "filter_query": query.urlencode(),
    })


def idea_detail(request, pk, *, comment_form=None, response_status=200):
    idea = get_object_or_404(public_ideas(), pk=pk)
    forum_access = get_forum_access(request.user)
    reply_target = None
    author_id = None
    if request.user.is_authenticated:
        author_id = Collaborator.objects.filter(user_id=request.user.pk).values_list("pk", flat=True).first()
    available_parents = replyable_comments(
        idea_id=pk, author_id=author_id,
    ).select_related("author")
    if comment_form is None:
        parent_id = request.GET.get("responder")
        if parent_id and forum_access["can_participate"]:
            try:
                parent_id = int(parent_id)
                if not 0 < parent_id <= 2**63 - 1:
                    raise ValueError
            except (TypeError, ValueError):
                raise Http404("Comentário inválido.")
            reply_target = get_object_or_404(available_parents, pk=parent_id)
        comment_form = CommentForm(initial={
            "parent_id": reply_target.pk if reply_target is not None else None,
        })
    else:
        parent_id = getattr(comment_form, "cleaned_data", {}).get("parent_id")
        if parent_id and 0 < parent_id <= 2**63 - 1:
            reply_target = available_parents.filter(pk=parent_id).first()
    target_id = request.GET.get("comentario", "")
    target_id = int(target_id) if target_id.isdecimal() and len(target_id) < 19 else None
    forum_page = get_forum_page(
        idea_id=pk, user=request.user, page_number=request.GET.get("page"),
        order=request.GET.get("ordem"), target_comment_id=target_id,
    )
    return render(
        request,
        "home/idea_detail.html",
        {
            "idea": prepare_public_idea(idea),
            "forum_access": forum_access,
            "staff_controls": {
                "can_moderate_comments": can_manage(request.user, "home.change_comment"),
                "can_deactivate_idea": can_manage(request.user, "home.change_ideasubmission"),
                "can_delete_idea": can_manage(request.user, "home.delete_ideasubmission"),
            },
            "comment_form": comment_form,
            "editor_initial": sanitize_message(comment_form["message"].value() or ""),
            "reply_target": (
                {"id": reply_target.pk, "public_name": reply_target.author.public_name, "excerpt": html.unescape(strip_tags(sanitize_message(reply_target.message)))[:200]}
                if reply_target is not None else None
            ),
            "forum_page": forum_page,
        },
        status=response_status,
    )
