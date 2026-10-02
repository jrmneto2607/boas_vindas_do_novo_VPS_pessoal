# Retomada do projeto Maflo Tech

Atualizado em 02/10/2026.

## Objetivo e próxima etapa

Criar um fórum público na página individual de cada ideia. Visitantes poderão ler as discussões; somente colaboradores cadastrados, com e-mail confirmado e participação liberada, poderão comentar e responder.

A parte de contas já está implementada. A próxima etapa é implementar o fórum: formulário, editor, regras de envio, listagem, respostas, denúncias e remoção pelo autor. Ainda não existem endpoints ou interface de participação no fórum.

## Preferências de trabalho

- O usuário prefere receber código com indicação objetiva de onde aplicar e do resultado esperado, acompanhado de uma breve explicação das classes e funções.
- Não editar arquivos por iniciativa própria. Apresentar o código para o usuário aplicar, a menos que ele autorize explicitamente a edição daquele trabalho. Nesta sessão ele autorizou diretamente a organização de forms, os ajustes visuais, a base comum, os links de acesso e a atualização deste arquivo.
- Manter o padrão visual do formulário da home nas telas de conta e no futuro fórum.
- Preservar o conteúdo, o parallax e o rodapé aprovados.
- Não fazer commit ou push sem pedido. Há alterações locais posteriores ao último commit.

## Decisões do fórum

- Cada comentário terá mensagem formatada e um campo GitHub opcional para exemplos ou versões do projeto.
- Editor com negrito, itálico, listas, cores e links. Sanitizar o HTML no servidor antes de qualquer exibição como HTML; a sanitização e o editor ainda não foram implementados.
- Nome ou pseudônimo público. E-mail obrigatório e confirmado; WhatsApp opcional. Contatos e registros de autorização são privados.
- Registrar preferência e autorização de contato sobre contribuições. Contato privado feito pela administração por e-mail ou WhatsApp; sem mensagens privadas ou chat interno.
- Primeira contribuição passa por aprovação. A administração pode liberar publicação direta por colaborador.
- Comentários com estados: pending, published, reported e disabled. Remoção pelo autor é separada, pelo campo removed_at.
- Respostas em um único nível, vinculadas ao comentário principal da mesma ideia.
- Autor pode remover o próprio comentário. Retirar o conteúdo da exibição pública, mantendo-o acessível à administração. Se houver respostas, mostrar apenas «Comentário removido pelo autor» e preservar a conversa.
- Duas denúncias de pessoas diferentes ocultam o comentário do público, deixando-o visível ao autor e à administração até avaliação.
- Uma denúncia por conta por comentário, com motivo obrigatório. Não permitir denunciar o próprio comentário.
- Implementar limites de envio, proteção contra abuso e verificar bloqueio da conta em todas as operações de participação.
- Centralizar a moderação em /organizador/.

## Implementado

### Ideias e apresentação

- Home, lista com filtros e página individual das ideias.
- Cards com PDF/GitHub clicáveis e link «Ver ideia».
- Texto quando a ideia não tem descrição: «Explore os materiais disponíveis para conhecer melhor este projeto.»
- home/templates/home/base.html compartilha cabeçalho, navegação, CSS, parallax e rodapé.
- index.html estende base.html, mantendo as seções e home.js somente na home. Avisos do envio de ideias continuam dentro do formulário da home.
- ideas_base.html estende base.html e define o layout container ideas-page para páginas de ideias e contas.
- Navegação compartilhada mostra Entrar/Criar conta para visitantes e Sair para usuários autenticados. Logout via POST com CSRF.

### Modelos e administração

- IdeaSubmission preservado.
- Collaborator vinculado ao usuário Django: nome público, e-mail único, WhatsApp, confirmação, autorização de contato, publicação direta e bloqueio.
- Comment vinculado à ideia, colaborador e comentário principal; conteúdo, GitHub e registros de moderação/remoção.
- CommentReport com motivo, detalhes e avaliação. Restrição única (comment, reporter) e índice de denúncias pendentes.
- Administração dos três modelos em home/admin.py. Aprovar/desativar registra o moderador e marca denúncias pendentes como avaliadas. Aprovação ignora comentários removidos pelo autor.
- Os modelos e controles administrativos existem, mas as regras públicas do fórum ainda não foram implementadas. clean() não é chamado automaticamente por save(); validar antes de salvar nas futuras operações.

### Contas

- home/forms/ideas.py contém IdeaSubmissionForm.
- home/forms/accounts.py contém RegistrationForm, ResendConfirmationForm, EmailAuthenticationForm e CollaboratorPasswordResetForm.
- home/forms/__init__.py está vazio. Os antigos forms.py e account_forms.py foram movidos; imports ajustados.
- home/account_views.py implementa cadastro, confirmação e reenvio.
- Cadastro cria usuário inativo com username interno aleatório e e-mail normalizado para minúsculas.
- Confirmação com link assinado válido por 24 horas; abrir o link não ativa a conta, é necessário confirmar por POST. Link reutilizado não reativa uma conta desativada após confirmação.
- Reenvio limitado a uma tentativa a cada cinco minutos por conta. Falha de envio preserva cadastro pendente. Proteção geral contra cadastros em massa ainda falta.
- Login por e-mail, logout e recuperação de senha com views do Django em home/urls.py. Recuperação limitada a colaboradores habilitados; link válido por uma hora.
- Login: botão Entrar e link Esqueci minha senha ao lado; abaixo, link azul «Ainda não tenho uma conta.».
- Cadastro: botão Cadastrar e somente o link azul «Já tenho uma conta.» abaixo.
- Reenviar confirmação aparece no formulário de login apenas após tentativa com senha correta de uma conta não confirmada e não bloqueada. Não aparece com senha errada ou e-mail inexistente. A conta permanece sem autenticação.
- Outros formulários de conta têm link de retorno ao login.
- form_fields.html compartilha campos, consentimento, ajuda e erros. Templates de conta e CSS seguem o formulário da home.

## E-mail e configuração

- O ambiente revisado está com DEBUG=True e EMAIL_BACKEND de console. E-mails aparecem nos logs, sem envio real.
- SMTP ainda não configurado (host, usuário e senha ausentes na revisão). Nunca imprimir ou versionar credenciais; .env está ignorado pelo Git.
- settings.py lê EMAIL_BACKEND do ambiente, mas docker-compose.yml ainda não repassa essa variável explicitamente. Acrescentar quando necessário escolher o backend pelo .env.
- Logs do backend de console podem quebrar URLs em quoted-printable: «=» no fim da linha indica continuação; reconstruir a URL sem essa quebra para testes locais.
- Ao preparar produção, conferir HTTPS e configuração do proxy para que os links de e-mail usem o domínio e protocolo corretos.

## Migrations e validação

- home/0001 até home/0006 estão aplicadas no PostgreSQL revisado.
- 0005_collaborator_comment_commentreport_and_more cria modelos, índices e restrição de denúncia única.
- 0006_collaborator_confirmation_sent_at adiciona o horário do último envio de confirmação.
- makemigrations --check --dry-run: sem diferenças. migrate --check: sem migrations pendentes.
- Verificadas as tabelas reais, confirmation_sent_at e restrições de unicidade.
- Ajustes recentes de templates, CSS e autenticação não exigiram novas migrations.
- manage.py check e git diff --check passaram após as últimas alterações.
- O usuário confirmou manualmente cadastro, confirmação, login, logout e recuperação de senha funcionando antes dos últimos ajustes de links.
- Verificações temporárias em banco SQLite em memória validaram cadastro, duplicidade, confirmação, reenvio, bloqueio, CSRF e o novo comportamento de login/CTA.
- Renderização das páginas e navegação anônima/autenticada também verificada.
- home/tests.py ainda não tem testes permanentes: manage.py test encontrou zero testes. Os testes temporários não substituem testes no PostgreSQL nem revisão visual no navegador.

## Git e ambiente

- Projeto: /home/neto/projetos/django-teste, no WSL Ubuntu-26.04.
- Caminho Windows: \\wsl.localhost\Ubuntu-26.04\home\neto\projetos\django-teste.
- Docker Compose: serviço web com Django/Gunicorn e db com PostgreSQL.
- Branch atual: main.
- Remoto: git@github.com:jrmneto2607/boas_vindas_do_novo_VPS_pessoal.git.
- Último commit local observado: 936bf56 — Organiza formulários e adiciona cadastro, confirmação de email e moderação.
- O push desse commit pelo agente falhou por autenticação SSH; o usuário informou que faria o envio com a senha da chave. Não assumir que foi concluído sem verificar.
- Login/recuperação, mudanças visuais e base comum posteriores ao commit estão locais, ainda sem novo commit na última verificação.
- Nesta sessão o terminal no sandbox falhou com «setup refresh had errors». Comandos pelo PowerShell chamando wsl fora do sandbox funcionaram com aprovação. rg não está instalado no WSL; foram usados find/grep.

## Comandos úteis

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web python manage.py showmigrations
docker compose run --rm web python manage.py migrate --check
```

Retomar lendo este arquivo e verificando os arquivos atuais. Próximo trabalho: fórum nas páginas individuais, respeitando a preferência de apresentar código antes de editar sem autorização.

## Atualização visual antes do fórum — 02/10/2026

- Login: recuperação de senha como botão com contorno verde-água; links de conta seguem a paleta do site.
- Cadastro: senha e confirmação antes da preferência e autorização de contato. Seletor com seta recuada; abertura animada nos navegadores compatíveis com appearance: base-select.
- Menu: Entrar destacado e Criar conta com contorno.
- Parallax original preservado. Fundo de leitura azul escuro rgba(11, 20, 32, 0.82), apenas entre menu e rodapé, com largura máxima de 1232px; conteúdo mantém sua largura original.
- Bordas em telas a partir de 1280px com desenho de circuito em content-circuit.svg. Terminais luminosos nos quatro cantos; bordas e terminais avançam 46px em direção ao menu e rodapé.
- Divisórias das seções limitadas à largura do fundo, com pontos nas pontas e brilho central. Divisória do rodapé combina com o degradê do topo.
- CSS servido com versão na URL para renovar o cache. Arquivos em staticfiles atualizados com collectstatic.
- Verificações antes do commit: git diff --check e manage.py check passaram. Aparência conferida pelo usuário ao longo dos ajustes.
- Usuário pediu um commit local antes de iniciar o fórum. Não realizar push sem pedido.