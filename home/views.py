from django.shortcuts import render
from .forms import IdeaSubmissionForm


# Create your views here.
def index(request):
    if request.method == 'POST':
        form = IdeaSubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data

    else:
        form = IdeaSubmissionForm()

    return render(
        request, 
        'home/index.html',
        {'form': form}
    )