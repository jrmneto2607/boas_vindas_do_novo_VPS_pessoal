from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from .forms import IdeaSubmissionForm
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

    return render(
        request, 
        'home/index.html',
        {'form': form}
    )