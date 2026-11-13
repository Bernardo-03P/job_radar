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
- `POST /api/v1/resumes/sources`: guarda um original opcional após ação explícita no
  site. `GET /sources` lista metadados; `DELETE /sources/{id}` exclui só o original.
  Exige identificação privada do navegador ou, nas consultas/exclusão, chave administrativa.
- `POST /api/v1/resumes/tailor-saved`: recebe `source_id` e um único `job_id`, exige
  chave administrativa e reutiliza validação/cache. Seleção JSON: 4 KiB, prazo,
  limite de concorrência e autenticação antes de ler o corpo.
- O upload multipart é limitado e interpretado em RAM antes do FastAPI. O PDF é lido
  por `BytesIO`, sem arquivo temporário em texto claro ou persistência do PDF no banco.
  Guardar o original é uma ação separada e opcional. O texto é enviado ao
  provedor de IA configurado, sujeito às políticas de retenção desse provedor.
- O retorno da IA é um plano com intervalos consecutivos dos índices das linhas do PDF
  (`source_range`, inclusivo). O backend mantém compatibilidade com o formato anterior
  de índices explícitos, mas rejeita misturar os dois formatos na mesma seção. O backend
  rejeita índices inventados, omitidos, repetidos e palavras-chave ausentes da vaga.
  O Markdown é construído pelo servidor a partir dos trechos originais.
- Se o plano for rejeitado pelas regras de evidências, há uma única tentativa de
  correção, limitada a 20 segundos. A segunda resposta passa pela mesma validação;
  conteúdo inválido nunca é salvo. Quebras de linha/espaços são normalizados somente
  para comparar palavras-chave, mantendo a redação original do currículo. O navegador
  aguarda até 150 segundos para cobrir o fluxo com correção e fallback de provedor.
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
não guarda o PDF original nem um campo separado com seu texto bruto. Se você escolher
**Guardar PDF para o Telegram**, uma cópia protegida por DPAPI do seu usuário Windows
fica em `.runtime/resume-vault`, separada do banco e fora do Git. Há um original por
identificação de navegador; guardar outro substitui essa cópia. A opção requer Windows.
**Consultar PDF guardado** e **Excluir PDF guardado** administram essa cópia no site.
Guardar não gera currículo nem chama a IA. Excluir não apaga o arquivo pessoal no
computador nem as versões já adaptadas. O navegador
mantém uma identificação privada aleatória em `localStorage`, nunca o PDF ou o
currículo nesse armazenamento. Navegadores/origens diferentes têm identificações
independentes. Limpar os dados do site perde essa identificação; o bot privado
continua podendo consultar as versões locais com a chave administrativa.
Outra descrição ou outro PDF exige uma versão compatível. Reenviar um PDF idêntico
permite recuperar as versões existentes sem consumir uma nova geração.

## Coleta de vagas reais

O coletor consulta a API pública Greenhouse e páginas públicas de carreiras Gupy,
sem chamadas de IA. As fontes atuais em `agent/job_sources.json` são RD Station
(Greenhouse) e Starian (Gupy). A página Gupy é consultada a cada execução; somente
estágios e trainee são detalhados, com leitura do JobPosting publicado e rejeição
de prazo vencido/aviso de encerramento. Não contorna autenticação ou bloqueios.
Referência da API: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board).

`agent/search_profile.json` registra o perfil autorizado: meta de 90% estágio e 10%
trainee em Dados/IA, Análise e Desenvolvimento de Sistemas e Suporte, priorizando N1.
N2 é secundário e exigências explícitas de experiência seguem para revisão. A proporção
depende das vagas disponíveis: o coletor não fabrica nem completa o lote com outros níveis.
Presencial/híbrido exige Florianópolis com evidência de localização na ilha; Estreito,
São José, Palhoça e demais arredores/continente ficam excluídos. Vagas remotas devem
aceitar Brasil e não apresentar restrição de residência incompatível identificada.
Endereços/bairros incertos ficam em `.runtime/collection-review.json`, sem importação.
Esses filtros são heurísticas textuais: revise endereço, elegibilidade e requisitos
na página original antes de se candidatar.

Na raiz do projeto, com o backend disponível para a etapa de importação:

```powershell
.venv/Scripts/python.exe -m agent.collect_jobs --limit 20
if ($LASTEXITCODE -ne 0) { throw "Coleta sem sucesso; importação cancelada." }
.venv/Scripts/python.exe agent/mock_crawler.py --input agent/collected_jobs.json
```

Use `--query Python` para filtrar título/descrição por trecho literal. O filtro de
localização adiciona um filtro sobre o campo publicado pela fonte. O perfil também
verifica requisitos de local e modalidade explícitos; não deduz trabalho remoto.
O coletor seleciona área e nível por termos explícitos, valida os registros no mesmo
schema da API e remove HTML da descrição. A lista de skills é um vocabulário limitado,
extraído por presença textual; não representa uma análise completa dos requisitos.
Salários e senioridade não são inferidos. Vagas afirmativas mantêm o título original.

`agent/collected_jobs.json` guarda o lote e `.runtime/collection-report.json` registra
horário UTC, fonte, filtros e contagens. Ambos ficam fora do Git. Falhas de rede ou
formato encerram com código 1; resultado vazio usa código 2. Não importe um arquivo
anterior após uma falha. A importação atualiza pela URL original, sem criar duplicatas.
Uma vaga presente no feed foi publicada pela empresa no momento da consulta, mas pode
ser encerrada depois. O coletor ainda não arquiva automaticamente vagas encerradas.

Em 13/11/2026, um lote exploratório de dez vagas do QuintoAndar validou a importação
e a preservação de IDs na repetição. Após a definição do perfil, essas vagas sênior
deixaram de aparecer na lista recomendada, sem apagar os registros anteriores.
Um estágio remoto em suporte da Starian foi validado e importado. A página não
informa N1/N2; essa classificação não foi inventada. RD Station não retornou vagas
compatíveis nessa consulta. As fontes atuais são um início, não uma busca exaustiva.

Site e helper Telegram consultam `GET /api/v1/jobs?matching_profile=true`, que filtra
antes de paginar. A consulta sem esse parâmetro mantém acesso aos registros históricos.
O importador JSON rejeita todo o lote antes do envio caso encontre vaga fora do perfil;
`--demo` continua sendo uma ação explícita separada. O cron existente foi atualizado
pela instalação da automação; editar apenas o JSON não altera um agendamento ativo.
URLs são normalizadas sem tracking, preservando identificadores como `jk` no Indeed.

### Descoberta em LinkedIn, Indeed e InfoJobs

Esses canais também foram pesquisados manualmente em 13/11/2026. Os resultados,
pendências de localização/elegibilidade e anúncios descartados estão em
[SEARCH_RESULTS.md](SEARCH_RESULTS.md). A vaga da Starian foi atualizada sem duplicar;
os demais resultados não foram importados automaticamente.

`agent/search_discovery.json` registra os canais e consultas preferidos. O cron instalado
consulta esses canais quando o acesso público e as ferramentas do Hermes permitirem.
São consultas públicas; login, captcha e bloqueios não são contornados. Sempre confira a
página original: nesta rodada, o anúncio da BeFly estava encerrado apesar dos agregadores.

## Hermes Agent

`agent/hermes_cron.json` é uma especificação do projeto. A instalação preserva o mesmo
Hermes, bot e provedor existentes. Para configurar uma instalação já pronta:

```powershell
.venv/Scripts/python.exe agent/mock_crawler.py --register-hermes
.venv/Scripts/python.exe -m agent.configure_automation
.venv/Scripts/python.exe agent/install_hermes_skill.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File agent/install_startup.ps1
hermes cron list
```

O job busca nos dias úteis às **09h de America/Sao_Paulo**, com `catch_up=on`:
horários perdidos são consolidados em uma execução. `JobRadar-Local-Startup` inicia
após login na mesma conta Windows e mantém um supervisor oculto, com verificação a
cada 15 minutos. Inicia Docker, backend e frontend já compilado quando necessário,
garante o gateway existente e recupera uma busca atrasada. Não funciona com o PC
desligado ou antes do login no Windows.

Locks e estado diário em `.runtime` evitam execução concorrente e avisos duplicados.
A recuperação tem intervalo mínimo de uma hora e até três tentativas por data. O
CLI Hermes instalado executa disparos manuais sincronamente; o supervisor aguarda
até 15 minutos e usa coleta determinística como contingência se o agente não concluir.
Esse resumo identifica cobertura reduzida. Nenhuma busca gera currículos.

O script envia um resumo ao dono fixo explicitamente autorizado no bot. O resultado
do Hermes fica local (`--deliver local`), evitando segundo aviso. Resposta Telegram
ambígua fica `unconfirmed` e não é reenviada automaticamente: confira o chat antes
de pedir novo envio. Tokens não são copiados para comandos, frontend ou Git.
Nenhum modelo/provedor do Hermes é alterado.

Diagnóstico e busca manual na raiz do projeto:

```powershell
.venv/Scripts/python.exe -m agent.daily_run --status
.venv/Scripts/python.exe -m agent.daily_run --run-now
```

O segundo comando pode enviar o resumo; `--no-notify` valida sem mensagem. A descoberta
complementar aceita `--input .runtime/hermes-candidates.json`, objeto com `checked_at`
ISO com fuso e `jobs`, limitado a oito horas de idade. Sites podem bloquear consultas;
não há bypass de login/captcha. O registro da tarefa Windows não é parte do CI.

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

Para uma rodada imediata, peça **“Busque novas vagas agora com meu perfil e mostre
os IDs e links.”** A skill diferencia consulta (`vagas`) de nova busca (`buscar`).
`buscar` exige DM do dono e executa a coleta com `--run-now --no-notify`, mesmo se a
rodada diária já terminou. O Hermes responde no chat atual, sem segundo aviso automático.
Quando houver descoberta web validada, usa `buscar --incluir-descoberta` com um lote
novo em `.runtime/telegram-candidates.json`. Sem ferramentas/acesso web, consulta
somente as fontes automáticas e informa a cobertura reduzida. Não gera currículo.

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
Para gerar pelo bot, selecione o PDF no site e clique em **Guardar PDF para o Telegram**.
No DM, peça “Gere meu currículo para a vaga 14”. O helper consulta as fontes guardadas
(`fontes`) e exige vaga e fonte antes de `gerar --job-id ... --source-id ... --confirmar`.
Se houver ambiguidade, o bot pergunta qual usar. O resultado fica no mesmo histórico
do navegador que guardou o original; repetir PDF/vaga/descrição usa cache.
O helper não recebe caminhos, não lê anexos Telegram e não oferece geração em lote.
`--local` não autoriza gerar. “Gerar e me enviar” também autoriza enviar a versão ao
mesmo DM, em Markdown. Consultar não chama o adaptador; o Hermes mantém seu provedor e cota.

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

### Operação temporária (preferência atual do proprietário)

Somente o Hermes permanece ativo. A tarefa Windows `JobRadar-Local-Startup` está
desativada: não há supervisor contínuo ligando o projeto no login.
O cron existente do Hermes continua às 9h nos dias úteis, com recuperação de atrasos.
Depois da descoberta pública, ele executa `agent.search_session --scheduled`,
que liga somente banco e API para importar as vagas e enviar o resumo; encerra
os recursos iniciados pela sessão em um bloco `finally`, mesmo em falhas normais.
O site não é iniciado pela coleta. Serviços já abertos manualmente são preservados.
O Docker Desktop pode continuar disponível para outros usos; o container do projeto
é parado, sem apagar banco ou volumes. Encerramento forçado do processo/PC pode
impedir o `finally`; consulte `.runtime/search-session.json` se houver interrupção.

A busca manual pelo helper do Telegram usa o mesmo ciclo. Para uma busca local:
`.venv/Scripts/python.exe -m agent.search_session --run-now`.
Para trabalhar no site, inicie os serviços manualmente. Com o banco/API parados,
consultas de currículos pelo bot ficam indisponíveis até sua próxima inicialização.
O instalador da tarefa Windows deixa o supervisor desativado por padrão;
`-Continuous` é uma opção explícita para mudar essa preferência.

As seções históricas abaixo descrevem a implantação anterior, continuamente ativa.

Em 13/11/2026 foram ativados cron com recuperação, supervisor Windows, aviso privado
e geração sob demanda pelo bot com original opcional protegido. O Hermes encontrou
o Programa de Estágio Tech.AI 2027 da Blip (ID 14) e confirmou o resumo no Telegram.
Starian (ID 13) foi preservada sem duplicação. A coleta passou de duas para nove
fontes configuradas, com leitura pública de Gupy e IEL/SC. A rodada mais recente
validou quatro vagas, incluindo EVOLUA/IEL (ID 15) e Geopixel (ID 16); duas ficaram
pendentes de revisão. A meta é dez vagas compatíveis por rodada, com faltantes
explícitos, preservando os filtros. O IEL revalida os anúncios configurados; a
descoberta de novos anúncios continua sendo complementada pelo Hermes.
Validação mais recente: 183 testes backend e 12 de navegador passaram (11 isolados
e um contra o site/backend reais), além de lint e Bandit.
Veja [AUDIT.md](AUDIT.md) e [VALIDATION.md](VALIDATION.md).

O processamento PDF usa subprocesso com prazo de 15 segundos, memória de 512 MiB e
limite de CPU de 10 segundos. O upload aceita até quatro requisições simultâneas e
tem prazo de recepção de 15 segundos. Essas configurações podem ser ajustadas no backend.
O projeto é destinado ao uso local; exposição pública exige autenticação de usuários,
HTTPS e políticas de operação próprias. Mantenha chaves e backups fora do Git.

Para os testes opcionais PostgreSQL, use exclusivamente um banco descartável chamado
`job_radar_audit` em loopback, configurado por `TEST_DATABASE_URL`. Cada teste cria e
remove somente seu próprio esquema temporário. O CI provisiona esse banco automaticamente.
