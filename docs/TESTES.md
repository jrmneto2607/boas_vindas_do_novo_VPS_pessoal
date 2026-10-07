# Guia de testes

Execute os comandos na raiz do projeto, no terminal WSL.

## Preparar

```bash
docker compose up -d db
```

O serviço web pode estar parado: `run --rm` cria um container temporário, executa os testes e o remove. As dependências precisam estar instaladas na imagem do projeto; se ainda não houver imagem, execute `docker compose build web`.

## Executar todos

```bash
docker compose run --rm web python manage.py test home.tests --noinput
```

O comando geral também descobre o mesmo conjunto:

```bash
docker compose run --rm web python manage.py test --noinput
```

## Executar por área

| Arquivo | O que verifica | Comando (após `docker compose run --rm web python manage.py test`) |
| --- | --- | --- |
| test_accounts.py | Cadastro, confirmação, reenvio, login, recuperação de senha e CSRF | `home.tests.test_accounts --noinput` |
| test_ideas.py | Vínculo, rascunho/PDF, envio anônimo, exclusão e bloqueios | `home.tests.test_ideas --noinput` |
| test_profile.py | Privacidade do perfil, contato e troca de senha | `home.tests.test_profile --noinput` |
| test_forum.py | Contribuições, respostas, sanitização, edição, denúncias e visibilidade | `home.tests.test_forum --noinput` |
| test_moderation.py | Permissões, moderação e contadores do Organizador | `home.tests.test_moderation --noinput` |

Exemplo completo:

```bash
docker compose run --rm web python manage.py test home.tests.test_accounts --noinput
```

Para executar somente um cenário, com mais detalhes:

```bash
docker compose run --rm web python manage.py test home.tests.test_accounts.AccountTests.test_confirmation_requires_post --noinput --verbosity 2
```

## Fluxos integrados

`docker compose run --rm web python manage.py test home.tests.test_workflows --noinput`

Verifica publicação de ideias, cadastro com retorno ao rascunho, exclusão do PDF após commit, descarte de denúncias e fuso horário.

## Dados e isolamento

- O Django cria um banco PostgreSQL de testes separado, normalmente `test_<nome-do-banco>`, e o remove ao terminar. O usuário do banco precisa de permissão para criar bancos.
- Os testes não utilizam os usuários e ideias do banco normal. Não altere DATABASES para apontar TEST.NAME ao banco real.
- `helpers.py` reúne fixtures compartilhadas de colaboradores e ideias. Não importa nem executa testes no funcionamento normal do site.
- Testes de envio de e-mail usam o backend em memória, sem enviar mensagens reais. Falhas de SMTP são simuladas.
- O cenário de upload usa uma pasta temporária, removida ao terminar.
- Não execute duas suítes simultaneamente contra o mesmo banco de testes.
- `--noinput` evita perguntas interativas; se sobrar um banco de testes de uma execução interrompida, o Django pode recriá-lo. Isso se refere exclusivamente ao banco de testes.

## Entender o resultado

- `OK`: todos os cenários executados passaram.
- `FAIL`: o resultado foi diferente do esperado; veja o nome do teste e a comparação.
- `ERROR`: ocorreu uma exceção; veja o traceback.
- Erro de conexão com `db`: confira se o serviço PostgreSQL está ativo.
- Erro de criação do banco: confira a permissão de criação de bancos do usuário configurado.

A suíte contém 111 cenários após esta reorganização. Testes automatizados não substituem revisão visual no navegador nem validam a entrega real de SMTP, HTTPS, backups e restauração.

## Adicionar testes

Use arquivos `test_*.py` na área correspondente, classes derivadas de `django.test.TestCase` e métodos `test_*`. Reutilize os helpers quando necessários. Para mudanças que exigem transações concorrentes, use `TransactionTestCase` e cenários próprios: a suíte atual não comprova o comportamento sob carga concorrente.

Nenhum teste deve usar credenciais reais, enviar e-mails externos ou depender de registros existentes no banco normal.


## Segurança e concorrência

```bash
docker compose run --rm web python manage.py test home.tests.test_security --noinput
```

Inclui PDFs inválidos/criptografados, acesso privado e URLs antigas, rascunhos temporários, limpeza e nova tentativa de exclusão, limites HTTP 429, preservação de bloqueios e dois envios simultâneos no PostgreSQL. O cenário concorrente usa TransactionTestCase e conexões independentes.
