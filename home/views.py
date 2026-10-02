from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from .forms.ideas import IdeaSubmissionForm
from .models import IdeaSubmission



# Create your views here.
def index(request):
    if request.method == 'POST':
        form = IdeaSubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data

            # Salvar os dados no banco de dados
            IdeaSubmission.objects.create(
                author_name=cleaned_data['author_name'],
                idea_title=cleaned_data['idea_title'],
                idea_pdf=cleaned_data['idea_pdf'],
                idea_github=cleaned_data['idea_github'],
                contact_email=cleaned_data['contact_email'],
                contact_whatsapp=cleaned_data['contact_whatsapp'],
                idea_consent=cleaned_data['idea_consent'],
                consent_accepted_at=timezone.now(),
            )

            messages.success(request, "Sua ideia foi enviada com sucesso!")

            return redirect(f"{reverse('home')}#enviar-ideia")

    else:
        form = IdeaSubmissionForm()

    # Obter todas as ideias enviadas, ordenadas por data de criação (mais recentes primeiro)
    ideas = IdeaSubmission.objects.all().order_by('-created_at', '-pk')
    # Obter ideias em destaque, limitando a 6 ideias aleatórias
    featured_ideas = IdeaSubmission.objects.filter(is_featured=True).order_by('?')[:6]

    return render(
        request, 
        'home/index.html',
        {
            'form': form,
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
    return IdeaSubmission.objects.values(*PUBLIC_IDEA_FIELDS)


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


def idea_detail(request, pk):
    idea = get_object_or_404(public_ideas(), pk=pk)

    return render(request, "home/idea_detail.html", {
        "idea": prepare_public_idea(idea),
    })
