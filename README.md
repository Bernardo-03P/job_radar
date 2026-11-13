# Tech Job Radar & Tailored Resume Matcher

Aplicação local com FastAPI, PostgreSQL 16/pgvector e Next.js App Router. Interface em PT-BR.

## Configuração no Windows (PowerShell)

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements.lock.txt
docker compose up -d --wait
```

Edite `.env`: configure `GROQ_API_KEY` e, opcionalmente, `OPENAI_API_KEY` para fallback.
O modelo Groq atual é `openai/gpt-oss-120b`, validado com a conta local. O Llama 3.3
previsto inicialmente retornou indisponibilidade e não apareceu na lista de modelos
acessíveis. Apesar do prefixo `openai/`, esse modelo roda na Groq e usa a chave Groq.
Se sua conta tiver outra disponibilidade, ajuste `GROQ_MODEL` após consultar os modelos
no console da Groq. Limites gratuitos variam por conta e modelo.
Defina uma `INGEST_API_KEY` própria e uma `RESUME_API_KEY` diferente para o Hermes.
Não coloque essas chaves nem chaves de IA no frontend.
Neste computador, `.env` usa `POSTGRES_PORT=55432` e a mesma porta em `DATABASE_URL`,
pois o Windows recusou a publicação de `5432`. O Compose aceita ambas por configuração.

Em um terminal, execute o backend:

```powershell
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Em outro, execute o frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Abra http://localhost:3000. Documentação da API: http://localhost:8000/docs.
Durante o desenvolvimento, use `npm run dev`. Para testar a versão de produção,
pare o servidor antes de executar `npm run build` e depois rode `npm run start`.
Não recompile a pasta `.next` enquanto `next start` estiver usando seus arquivos:
isso pode quebrar o carregamento do JavaScript e deixar os controles sem resposta.
O frontend usa `http://localhost:8000` por padrão. Para alterar, configure
`NEXT_PUBLIC_API_URL` em `frontend/.env.local` e reinicie/recompile o frontend.

Para inserir exemplos **fictícios**, sem gastar tokens:

```powershell
.venv/Scripts/python.exe agent/mock_crawler.py --demo
```

## Comportamento e limites

- `GET /api/v1/jobs`: lista, busca por `q`, pagina com `limit` e `offset`.
- `POST /api/v1/jobs`: ingestão autenticada por `X-API-Key`; atualiza pela URL original.
- `POST /api/v1/resumes/tailor`: recebe `resume_file`, `job_description` e `job_id`
  opcional em multipart. Exige `X-Resume-Token`, salva a versão e devolve `version`.
  Mesmo PDF, vaga e descrição reutilizam a versão salva (`cached=true`), sem IA.
- `GET /api/v1/resumes/versions`: histórico privado; `GET /versions/{id}` consulta,
  `GET /versions/{id}/markdown` baixa e `DELETE /versions/{id}` exclui uma versão.
  Todas essas rotas ficam sob `/api/v1/resumes` e exigem identificação privada do
  navegador (`X-Resume-Token`) ou chave administrativa do Hermes (`X-API-Key`).
- PDF: até 5 MiB, até 100 páginas e 60 mil caracteres; PDFs sem texto e criptografados são rejeitados.
- O upload multipart é limitado e interpretado em RAM antes do FastAPI. O PDF é lido
  por `BytesIO`, sem arquivo temporário ou persistência no banco. O texto é enviado ao
  provedor de IA configurado, sujeito às políticas de retenção desse provedor.
- O retorno da IA é um plano de organização com índices das linhas do PDF. O backend
  rejeita índices inventados, omitidos, repetidos e palavras-chave ausentes da vaga.
  O Markdown é construído pelo servidor a partir dos trechos originais.
- **Modo conservador:** preserva a redação original e reorganiza blocos contíguos.
  Não implementa paráfrase livre nem cria frases STAR: isso evita acrescentar fatos,
  mas limita a reescrita solicitada. STAR só pode aparecer se já estiver no texto.
  Revise o agrupamento dos blocos antes de enviar o currículo.
- O índice mede presença textual das palavras-chave extraídas, sem embeddings e sem
  previsão de aprovação ATS. A coluna vetorial está preparada para uso posterior;
  nenhum embedding é gerado neste projeto.
- Sem chaves configuradas, adaptar retorna HTTP 503. Falhas de ambos os provedores
  retornam uma explicação segura em português: saldo/cota/autenticação indisponíveis
  usam HTTP 503, excesso temporário de chamadas usa HTTP 429 e resposta JSON inválida
  ou sem evidências usa HTTP 502. Não há chamadas reais de IA nos testes.
- O startup aplica as migrações Alembic versionadas, com bloqueio para inicializações
  simultâneas. A primeira migração adota as tabelas anteriores sem apagar os dados.
  Faça backup do volume antes de atualizar. Downgrade destrutivo não é automático.

## Currículo sob demanda por vaga

1. Adicione o PDF, selecione uma vaga e clique em **Adaptar meu currículo**.
2. A versão fica vinculada ao PDF e à descrição usada. As vagas prontas são marcadas.
3. Ao alternar entre vagas, os resultados são reutilizados sem gerar novamente.
4. Use **Baixar Markdown** para obter o arquivo da versão selecionada.
5. O histórico **Versões salvas por vaga** permite abrir e excluir versões mesmo
   depois de recarregar a página, sem enviar de novo o PDF para consultar o texto.

O banco local guarda o texto adaptado, descrição da vaga e hashes de identificação;
não guarda o PDF original nem um campo separado com seu texto bruto. O navegador
mantém uma identificação privada aleatória em `localStorage`, nunca o PDF ou o
currículo nesse armazenamento. Navegadores/origens diferentes têm identificações
independentes. Limpar os dados do site perde essa identificação; o bot privado
continua podendo consultar as versões locais com a chave administrativa.
Outra descrição ou outro PDF exige uma versão compatível. Reenviar um PDF idêntico
permite recuperar as versões existentes sem consumir uma nova geração.

## Hermes Agent

`agent/hermes_cron.json` é uma especificação do job do projeto, não uma cópia do arquivo
interno do Hermes. Com o Hermes instalado, configurado com navegação web e credenciais
de inferência, registre explicitamente:

```powershell
.venv/Scripts/python.exe agent/mock_crawler.py --register-hermes
hermes cron list
```

Mantenha o backend e o gateway/scheduler do Hermes em execução. O job busca vagas nos
dias úteis às 09h de São Paulo, gera JSON e usa o endpoint de ingestão. A execução real
do agente não faz parte do CI e depende das fontes e ferramentas disponíveis no Hermes.
Para usar Hermes dentro do WSL, adapte os caminhos e o Python do prompt ao ambiente Linux.
O registro não é automático para evitar criar tarefas recorrentes sem o runtime configurado.
Se o Hermes já estiver instalado e funcionando, use essa mesma instalação e perfil.
O comando não instala nem inicia outro gateway, não muda seu modelo ou provedor e
entrega o resultado apenas localmente (`--deliver local`). A configuração OpenAI do
projeto não é carregada no processo de registro, preservando o ambiente do Hermes.

Referência: [Scheduled Tasks — Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

## Consulta pelo Telegram do Hermes

A skill local `job-radar` usa o **mesmo Hermes e bot existentes**. Configure no `.env`
`RESUME_API_KEY`, `JOB_RADAR_HERMES_HOME` e `JOB_RADAR_TELEGRAM_OWNER_ID` com o ID do
proprietário privado já autorizado no bot. A instalação local foi configurada com o
único usuário de `TELEGRAM_ALLOWED_USERS`, sem expor ou trocar o token do Telegram.

```powershell
.venv/Scripts/python.exe agent/install_hermes_skill.py
hermes gateway restart
```

No chat **privado** do seu bot, envie `/job_radar` e depois, por exemplo:

- “Mostre as vagas Python do meu Job Radar.”
- “Liste meus currículos adaptados.”
- “Me envie o currículo salvo para a vaga Backend Python.”
- “Mostre o índice de coincidência da versão para essa vaga.”

O helper verifica plataforma Telegram, DM e IDs do chat e remetente. Rejeita grupos,
canais, outros usuários e contexto de sessão ausente. O envio usa `sendDocument`
para o destino privado fixo, com Markdown em memória e somente quando solicitado.
Não altera o provedor/modelo do Hermes nem configura um segundo gateway.

Para diagnóstico no terminal do PC, sem enviar mensagens:

```powershell
.venv/Scripts/python.exe agent/hermes_bridge.py --local status
.venv/Scripts/python.exe agent/hermes_bridge.py --local curriculos
```

O `--local` é rejeitado dentro de sessões do Hermes e não autoriza envio no Telegram.
O bot consulta versões já geradas; para adaptar um currículo novo, use o upload do
site. Essa consulta não chama o adaptador de IA novamente; a interpretação da conversa
pelo próprio Hermes segue o provedor e os limites que você já usa nele.

## Verificações

```powershell
.venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements-dev.lock.txt
.venv/Scripts/python.exe -m pytest backend/tests -v -c backend/pyproject.toml
.venv/Scripts/python.exe -m ruff check backend agent
cd frontend
npm run lint
npm run build
npm run test:e2e
```

Os testes usam PDFs válidos gerados em memória, mocks de IA e SQLite isolado para rotas.
Conexões externas são bloqueadas; loopback permanece disponível para o event loop do Windows.
O GitHub Actions executa testes/lint do backend e lint/build do frontend.
Os testes Playwright verificam o seletor de PDF, a busca, a seleção da vaga e o
resultado de adaptação com IA mockada. Usam uma instância de teste na porta 3100.
Também cobrem troca entre vagas, cache por currículo/descrição, download e histórico
após recarregar. O envio ao Telegram é testado com mocks, sem mensagens reais no CI.
No Windows, usam o Edge instalado. No CI, usam Chromium instalado pelo Playwright.

Para parar o PostgreSQL preservando os dados: `docker compose stop`.

## Estado da coleta e auditoria

A coleta de vagas reais ainda precisa ser validada. A execução diária com recuperação
ao ligar o PC e a geração de novos currículos pelo Telegram são próximas etapas;
o bot atualmente consulta e envia versões já salvas. A geração continuará sob demanda,
somente para vagas escolhidas. Veja [AUDIT.md](AUDIT.md).

O processamento PDF usa subprocesso com prazo de 15 segundos, memória de 512 MiB e
limite de CPU de 10 segundos. O upload aceita até quatro requisições simultâneas e
tem prazo de recepção de 15 segundos. Essas configurações podem ser ajustadas no backend.
O projeto é destinado ao uso local; exposição pública exige autenticação de usuários,
HTTPS e políticas de operação próprias. Mantenha chaves e backups fora do Git.

Para os testes opcionais PostgreSQL, use exclusivamente um banco descartável chamado
`job_radar_audit` em loopback, configurado por `TEST_DATABASE_URL`. Cada teste cria e
remove somente seu próprio esquema temporário. O CI provisiona esse banco automaticamente.
