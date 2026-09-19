from django.http import HttpResponse

# Create your views here.
def index(request):
    return HttpResponse("Bem vindo a minha biblioteca de Projetos - atualizando automaticamente.")