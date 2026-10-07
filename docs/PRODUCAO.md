# Operação e configuração de produção

## Ambientes

O ambiente local continua usando `config.settings` e a opção DJANGO_DEBUG atual. Para produção, configure no .env:

```dotenv
DJANGO_SETTINGS_MODULE=config.production
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=seu-dominio.example
CSRF_TRUSTED_ORIGINS=https://seu-dominio.example
TRUST_PROXY_HTTPS=true
RATE_LIMIT_TRUSTED_PROXIES=IP_INTERNO_DO_PROXY
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

Preencha o domínio e o IP corretos antes de usar. TRUST_PROXY_HTTPS só deve ser true quando o proxy confiável sobrescrever X-Forwarded-Proto; RATE_LIMIT_TRUSTED_PROXIES exige que esse proxy sobrescreva X-Real-IP. Sem esses valores, o Django não confia nos cabeçalhos de origem enviados pelo cliente.

O perfil de produção força HTTPS, desliga DEBUG, usa cookies seguros e HSTS inicial de uma hora. HSTS para todos os subdomínios e preload ficam desativados intencionalmente: ativar somente quando todos os subdomínios e certificados estiverem preparados. O diagnóstico pode apontar dois avisos relativos a essas opções.

```bash
docker compose run --rm web python manage.py check --deploy --settings=config.production
```

SMTP deve ser preenchido e testado com o provedor real. Não versione .env. Backups e restauração continuam sendo uma etapa operacional própria.

## Uploads e acesso

Nunca configure nginx, CDN ou outro servidor para entregar MEDIA_ROOT ou private_uploads diretamente. Encaminhe `/media/` e `/ideias/<id>/pdf/` para o Django. Ele permite PDFs de ideias ativas/aprovadas ao público e PDFs pendentes/desativados apenas ao dono e administradores com permissão. Os arquivos são entregues como download, com no-store e nosniff. URLs antigas passam pela mesma validação.

PDFs novos precisam ter estrutura legível, ao menos uma página, extensão PDF, tamanho máximo de 10 MB e não podem estar criptografados. Esta validação não é um antivírus. No proxy configure limite de requisição compatível (por exemplo, 12 MB).

Rascunhos ficam em private_uploads/drafts; a sessão guarda somente ID e validade. O prazo é uma hora, estendido para 24 horas durante cadastro. Rascunhos antigos em base64 são convertidos no próximo acesso, se ainda válidos.

## Limpeza periódica

O serviço cleanup executa a cada 15 minutos: expiração dos rascunhos, repetição de exclusões que falharam, limpeza dos contadores expirados e das sessões expiradas. Ele usa o banco e os diretórios do mesmo projeto.

```bash
docker compose up -d --build web cleanup
docker compose logs --tail=30 cleanup
```

Para executar manualmente:

```bash
docker compose run --rm web python manage.py cleanup_uploads
docker compose run --rm web python manage.py clearsessions
```

A exclusão de PDFs só ocorre após commit. Arquivos substituídos também entram na fila; uma falha de armazenamento mantém a tarefa para nova tentativa. A limpeza não apaga arquivos ainda referenciados.

## Limites de requisição

Limites compartilhados por todos os workers no PostgreSQL, por IP e, quando disponível, conta/e-mail:

| Fluxo | Limite |
| --- | --- |
| Cadastro | 10 por hora |
| Login | 20 a cada 5 minutos |
| Recuperação de senha | 5 por hora |
| Reenvio de confirmação | 10 por hora, além do intervalo individual existente |
| Envio/rascunho de ideia | 20 por hora |

Requisições excedentes recebem HTTP 429 e Retry-After. RATE_LIMITS permite ajustar os valores. Proteção não substitui limites de conexão e tamanho no proxy.

Cada formulário possui token assinado de envio. O banco serializa requisições com o mesmo token, evitando duplicidade inclusive em envios simultâneos; um novo formulário permite um novo envio intencional.

## Imagem e persistência

.dockerignore exclui .env, uploads, banco SQLite e backups. O build não deve conter esses dados. O Compose local usa bind mount da pasta do projeto: isso permite leitura de .env em tempo de execução e é diferente de copiar segredos para a imagem. Preserve media/, private_uploads/ e o volume PostgreSQL ao mover o projeto. Faça backups do banco e dos PDFs publicados/preservados.
