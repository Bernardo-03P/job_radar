# Guia operacional

## Configuração local

Copie `.env.example` para `.env`. O arquivo real não é versionado. Backend e scripts leem a configuração a partir da raiz do projeto.

| Variável | Finalidade |
| --- | --- |
| `DATABASE_URL` | Conexão SQLAlchemy com PostgreSQL local |
| `POSTGRES_PORT` | Porta do container publicada em loopback; deve coincidir com `DATABASE_URL` |
| `INGEST_API_KEY` | Autoriza a ingestão de vagas |
| `RESUME_API_KEY` | Chave administrativa distinta, usada pelo helper privado |
| `GROQ_API_KEY`, `GROQ_MODEL` | Provedor principal e modelo disponível na conta |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Fallback opcional |
| `CORS_ORIGINS` | Origens locais permitidas na interface |
| `JOB_RADAR_HERMES_HOME` | Instalação existente do Hermes, sem incluir tokens em argumentos |
| `JOB_RADAR_TELEGRAM_OWNER_ID` | Identificador do único proprietário autorizado |

`NEXT_PUBLIC_API_URL` pertence a `frontend/.env.local` se precisar mudar o endereço padrão da API. O prefixo `NEXT_PUBLIC_` torna valores acessíveis ao navegador; não o utilize para segredos.

O token Telegram permanece na configuração do Hermes existente. O projeto não exige copiá-lo para o frontend nem publica esse arquivo.

## Inicialização manual

```powershell
docker compose up -d --wait
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Em outro terminal, `cd frontend` e `npm run dev -- --hostname 127.0.0.1`. Para produção local, pare o servidor, execute `npm run build` e depois `npm run start -- --hostname 127.0.0.1`. Não reconstrua `.next` enquanto uma instância de produção estiver utilizando os arquivos.

Para parar o banco sem apagar dados: `docker compose stop`. Não use remoção de volumes para desligamento cotidiano.

## Coleta

```powershell
# Consulta fontes públicas, aplica o perfil e salva relatórios locais
.venv/Scripts/python.exe -m agent.collect_jobs --limit 50

# Liga API/banco, coleta/importa e encerra recursos próprios
.venv/Scripts/python.exe -m agent.search_session --run-now

# Mesma operação sem resumo Telegram
.venv/Scripts/python.exe -m agent.search_session --run-now --no-notify
```

O segundo comando pode enviar um resumo ao proprietário configurado. O terceiro é apropriado para conferência local sem mensagens. Nenhum deles gera currículo ou faz candidatura.

O perfil de exemplo usa Florianópolis/ilha ou remoto no Brasil, estágios prioritários, disponibilidade a partir das 12h e meta de dez confirmadas. Esses critérios são editáveis em `agent/search_profile.json`; não são uma garantia de quantidade disponível.

Vagas sem turno, mas compatíveis com os demais critérios, aparecem em **Horário a confirmar**. Vagas com jornada incompatível ficam excluídas. Endereço da sede institucional não confirma o endereço específico de uma vaga.

O lote complementar de descoberta é um JSON em `.runtime`, com `checked_at` ISO 8601 e `jobs`. Deve ser recente e conter somente fatos verificáveis. O importador não deve consumir resultados antigos após uma falha de coleta.

## Hermes e Telegram opcionais

Use uma instalação do Hermes já configurada para o proprietário. O projeto não altera automaticamente o modelo ou o provedor do Hermes.

```powershell
# Registra uma única tarefa de coleta, se ainda não houver uma com o mesmo nome
.venv/Scripts/python.exe -m agent.mock_crawler --register-hermes

# Atualiza somente a tarefa existente com recuperação e fluxo atual
.venv/Scripts/python.exe -m agent.configure_automation

# Instala a skill na instalação existente
.venv/Scripts/python.exe agent/install_hermes_skill.py

# Windows: tarefa SEM gatilhos, iniciada pelo helper quando houver um pedido
./agent/install_interactive_session.ps1
```

O cron de exemplo é 9h nos dias úteis, no fuso `America/Sao_Paulo`, com recuperação quando o ambiente ficar disponível. PC e Hermes precisam estar disponíveis para executar a tarefa. Não há serviço na nuvem neste repositório.

O helper pode ser invocado pelo Hermes com:

```powershell
.venv/Scripts/python.exe agent/hermes_bridge.py vagas
.venv/Scripts/python.exe agent/hermes_bridge.py fontes
.venv/Scripts/python.exe agent/hermes_bridge.py gerar --job-id ID --source-id UUID --confirmar
```

Os exemplos de geração exigem um ID real selecionado pelo proprietário. O helper verifica as variáveis de contexto confiáveis do Hermes antes de iniciar serviços ou acessar dados. Não invente nem substitua esse contexto. `--local` é diagnóstico humano fora do Hermes e não autoriza geração ou envio como se fossem pedidos do Telegram.

Comandos interativos autorizados iniciam site, API e banco. O prazo de cinco minutos começa após o comando terminar; novos pedidos renovam o prazo. Gerações em andamento são protegidas e polling GET não renova o prazo. Recursos que já estavam abertos manualmente são preservados.

A tarefa antiga `JobRadar-Local-Startup` permanece desativada por padrão; `-Continuous` no instalador antigo é uma opção explícita para operação contínua, não o modo padrão.

## Documento original e histórico

- O upload temporário aceita PDF com texto selecionável, até 5 MiB.
- Guardar o original no site é uma ação explícita e separada da adaptação.
- O cofre guarda original e identificação de acesso com DPAPI do usuário do Windows; não funciona como cofre portátil para outra conta ou sistema.
- O histórico adaptado é privado e fica no banco local. O navegador mantém a identificação privada usada para consultar suas versões.
- Limpar os dados do navegador pode remover essa identificação. Não publique, copie ou compartilhe o token para contornar esse vínculo.
- O cache depende do conteúdo do PDF, da vaga e da descrição. Alterações nesses dados podem exigir nova adaptação.
- Encerramento forçado do processo ou do PC pode impedir uma finalização normal. Os arquivos de diagnóstico em `.runtime` registram o estado das sessões sem compor o repositório público.

## IA e evidências

O provedor recebe o texto da vaga e do currículo. A resposta é um plano de seções com intervalos de linhas; o servidor exige cobertura completa, sem omissões ou repetições, e verifica as palavras-chave contra a vaga. Existe uma única tentativa limitada de correção de evidências. Uma resposta inválida não é salva como currículo adaptado.

O resultado não implementa reescrita livre, criação de fatos ou narrativas STAR ausentes no original. Mudanças factuais no currículo devem ser feitas no documento fonte.

## Diagnóstico

| Sintoma | Conferir |
| --- | --- |
| API indisponível | `/health`, Docker e a porta de `DATABASE_URL` |
| Controles do site sem resposta após build | Recompilar com `next start` parado e reiniciar a instância |
| Falha de adaptação | Chave/modelo do provedor, limites e validação de evidências; a mensagem não deve expor o documento |
| Helper não inicia serviços | Instalação da tarefa interativa e contexto privado do proprietário |
| Busca sem dez confirmadas | Relatório de fontes, restrições do perfil e grupo de horário pendente; não completar com anúncios incompatíveis |

Não publique logs locais ou capturas do navegador com dados pessoais ao abrir um relato de problema. O projeto inclui uma captura reproduzível com dados fictícios para documentação.
