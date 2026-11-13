# Validação — 12/11/2026

**Atualização final em 13/11/2026:** automação, recuperação, avisos privados e geração
sob demanda pelo bot implementados. 183 testes backend e 12 de navegador passaram.
Os registros anteriores preservam o estado histórico de cada etapa; veja a evidência final ao fim.

## Auditoria final local

### Ampliação das fontes e fechamento em 13/11/2026

- Nove fontes configuradas: RD Station, Starian, Softplan, Geopixel, Leega, Smarthis
  e três anúncios públicos IEL/SC. Portais sem vagas compatíveis não aumentam a contagem.
- IEL exige campos originais e candidatura disponível; página encerrada retorna
  zero. Bairro ausente vai para revisão, sem aproveitar endereço do rodapé.
- Gupy sem JSON-LD usa estado público Next com identidade da vaga/empresa, status,
  publicação externa, validade e requisitos completos verificados.
- Rodada real às 17h36: quatro selecionadas, uma nova (Geopixel ID 16), duas em
  revisão, nove fontes responderam sem falhas. Meta dez, faltantes seis. Não houve
  novo envio ao Telegram nem geração de currículo. Estado `sent` é do aviso anterior.
- Suíte final: **183 passaram em 25,21 segundos**, incluindo PostgreSQL descartável
  em `127.0.0.1:55432`, banco `job_radar_audit`; nenhum teste ignorado.
- Navegador: 11 testes isolados passaram; o teste opcional passou separadamente
  contra o site real na porta 3000. A tentativa na origem isolada 3100 foi bloqueada
  pelo CORS do backend; nenhuma origem adicional foi liberada para fazer o teste passar.
- ESLint, Ruff, Bandit médio/alto e scanner de publicação aprovados.
- Supervisor reiniciado e Running; gateway existente respondeu com código zero.
  Chamada agendada retornou `already_completed`, sem duplicar resumo.
  Próxima execução: segunda-feira, 16/11/2026, 09h de São Paulo. Essa execução
  futura ainda não foi observada e depende do PC/serviços e acesso às fontes.

- Python 3.14 no Windows: 81 testes backend passaram em 16,46 segundos.
- PostgreSQL 16/pgvector descartável: migrações concorrentes, adoção de dados e locks passaram.
- Ruff em backend, agent e scripts: passou.
- Bandit médio/alto: passou; subprocessos revisados.
- pip-audit nos locks e npm audit: nenhuma vulnerabilidade conhecida encontrada.
- ESLint, TypeScript e build de produção Next.js: passaram.
- Playwright: servidor isolado na porta 3100, dados sintéticos e IA mockada.
  Teste opcional da API pessoal desabilitado enquanto o site permanece desligado.
- Scanner do índice Git: segredos, banco e documentos pessoais excluídos.

O CI instala Python com hashes e provisiona PostgreSQL descartável. Executa testes,
lint, checagem de segredos e análise de dependências. Frontend: Node 22, npm ci,
lint/build e Chromium. O resultado remoto deve ser acompanhado no GitHub.

## Validações funcionais anteriores

Um PDF fictício validou Groq e persistência com cache antes da auditoria. O modelo
openai/gpt-oss-120b respondeu pela Groq; o Llama inicialmente previsto estava
indisponível nessa conta. OpenAI retornou saldo esgotado, sem sucesso real validado.
Durante a auditoria, IA e Telegram foram mockados, sem mensagens reais ou inferência.

O defeito anterior de upload/busca vinha de um chunk JavaScript inválido após
recompilar .next com next start ativo. Build seguido de reinício restaurou a interface.
Os testes de interação usam o build de produção em uma instância isolada.

A skill do Hermes existente consulta e envia versões salvas no chat privado autorizado.
Foi atualizada para bash/PowerShell sem reiniciar o gateway durante a auditoria.

Site, backend e banco pessoais permanecem parados a pedido do proprietário.
Veja AUDIT.md para correções, limitações e funcionalidades pendentes.

Playwright final: 10 testes passaram em 11,5 segundos; 1 teste opcional da API pessoal desabilitado.

## Coleta real — 13/11/2026

- Nova coleta sem IA pela API pública Greenhouse, com validação pelo schema da API.
- Grupo QuintoAndar: 100 registros recebidos; filtro tech e localização Brasil;
  dez selecionados pelo limite explícito. Nenhum registro inválido nesse retorno.
- Nubank retornou uma lista vazia na consulta exploratória e não foi configurado.
- Dez vagas reais importadas no PostgreSQL local, IDs 3 a 12.
- Segunda importação preservou IDs e manteve o total em 12, incluindo duas demonstrações.
- Relatório local em `.runtime/collection-report.json`, fora do Git.
- Treze novos testes cobrem HTML, evidências ausentes, URL original, filtros,
  duplicatas, limite, falhas HTTP e formato inesperado. Todos passaram.
- Suíte backend: 91 passaram, três testes opcionais PostgreSQL ignorados por falta
  de `TEST_DATABASE_URL`. Houve um aviso de permissão no cache do pytest; nenhum teste falhou.
- Ruff em backend, agent e scripts passou.
- Agendamento com recuperação, avisos e geração pelo Telegram continuam pendentes.
- Nenhuma geração de currículo ou mensagem de Telegram foi realizada nesta validação.

### Perfil e primeira vaga compatível

- Preferências registradas em `agent/search_profile.json`: meta 90% estágio/10% trainee;
  Dados/IA, Análise e Desenvolvimento de Sistemas, Suporte N1 prioritário e N2 iniciante.
- Presencial/híbrido somente com evidência de bairro da ilha de Florianópolis;
  Estreito, continente e municípios vizinhos excluídos; remoto com elegibilidade no Brasil.
- Endereços incertos e exigência obrigatória de experiência N2 seguem para revisão,
  sem importação automática. O filtro é textual e não substitui a revisão da vaga original.
- RD Station: quatro vagas consultadas, nenhuma no nível desejado.
- Starian: descoberta de estágio pela página pública de carreiras; JobPosting
  confirma estágio de suporte remoto em território nacional. Registro local ID 13.
  A página não classifica N1/N2. Prazo publicado: 11/12/2026.
- API com `matching_profile=true` devolveu somente o estágio compatível; histórico mantido.
- O importador JSON valida o perfil inteiro antes de enviar qualquer vaga.
- Site e helper Telegram passaram a usar a lista recomendada. Sem envio real ao Telegram.
- Testes cobrem exclusões geográficas, bairro desconhecido, restrições de residência,
  níveis/áreas, N2, meta 90/10, paginação após filtragem, descoberta em página de carreiras,
  JobPosting vencido/encerrado e tradução oculta que não deve encerrar uma vaga aberta.
- Backend final: 116 testes passaram, três opcionais PostgreSQL ignorados por falta
  de `TEST_DATABASE_URL`; os 38 testes de coleta/perfil estão incluídos nesse total.
- Frontend: lint, TypeScript, build e os 11 testes de navegador passaram, incluindo
  API real com a vaga da Starian na origem local de produção (porta 3000).
  A origem isolada 3100 não consta no CORS
  pessoal; a integração real deve usar `E2E_EXTERNAL_SERVER=1` e `E2E_REAL_API=1`.

### Rodada complementar e canais preferidos — 13/11/2026

- Coleta automática repetida com limite 30: RD Station sem correspondências, estágio
  Starian atualizado no ID 13, sem inserção duplicada.
- LinkedIn, Indeed e InfoJobs pesquisados; candidatos e motivos de revisão registrados
  em SEARCH_RESULTS.md. Nenhuma candidatura ou mensagem foi enviada.
- BeFly descartada após confirmar "Applications closed" na página original. Geopixel
  não produziu registro verificável na exploração e não foi adicionada às fontes.
- Detector de encerramento cobre inglês; descoberta não confunde "Internacional"
  com estágio. Testes de regressão: 39 testes de coleta/perfil passaram; Ruff passou.
- `search_discovery.json` e prompt Hermes registram os canais preferidos, sem alterar
  agendamentos ativos. Automação, avisos e geração pelo Telegram continuam pendentes.
- Limpeza/otimização e auditoria final em duas rodadas ficam após as funcionalidades;
  não foram declaradas concluídas nesta etapa.

## Validação final — automação e auditoria em duas rodadas

- Cron existente `74fa3bc568e6`: ativo, `0 9 * * 1-5`, `America/Sao_Paulo`, catch-up ativo.
  Próxima execução observada: 16/11/2026 às 09h, segunda-feira.
- `JobRadar-Local-Startup`: Running; supervisor oculto, usuário interativo atual,
  verificação a cada 15 minutos, serviços prontos, recuperação `already_completed`.
- Hermes real: duas vagas selecionadas, uma nova (Blip ID 14), três candidatas
  filtradas, fontes automáticas sem falhas, Telegram `notification_status=sent`.
  Bloqueios LinkedIn/Indeed/InfoJobs relatados pelo agente, sem bypass.
- Geração exige fonte guardada e vaga escolhida; nenhuma geração automática acionada.
  Inferência de adaptação mockada para evitar custo e uso de documentos pessoais.
  DPAPI validada de verdade com dados sintéticos.
- **151 testes backend passaram em 19,46 s**, sem skips, com PostgreSQL descartável.
  Testes removeram somente schemas temporários `audit_*`, sem tocar no banco pessoal.
- **12 testes de navegador passaram em 18,4 s**, build de produção e API pessoal para
  leitura de vagas. Upload/cofre/adaptação usam mocks e arquivos sintéticos.
- Ruff, Bandit médio/alto, ESLint, TypeScript e build aprovados. pip-audit e npm audit:
  nenhuma vulnerabilidade conhecida. Scanner do worktree inclui arquivos novos.
- Limpeza/otimização: URLs sem tracking, cache, limites de corpo, gravações atômicas,
  erros sanitizados, recuperação limitada e documentação alinhada à versão final.
- Disparo manual adicional Hermes falhou; não contou como sucesso, não apagou o estado
  confirmado e não provocou aviso duplicado. Há contingência sem IA.
- Sem reinício físico do PC e sem nova geração real de currículo pessoal. Artefatos
  privados e logs ficam em `.runtime`, ignorados pelo Git. Alterações desta etapa estão
  locais; não houve nova publicação ou execução remota do CI.

## Correção de rejeição de evidências — 13/11/2026

- Reproduzida com IA real e currículo fictício de 34 linhas: um grupo não consecutivo
  e duas palavras-chave ausentes literalmente da vaga, sem linhas omitidas/repetidas.
- Prompt passou a exigir intervalos inclusivos consecutivos, cobertura exata e cópia
  literal das palavras-chave. O formato reduz o tamanho do plano para currículos longos.
- Validador continua rejeitando intervalos inválidos, bool como índice, sobreposição,
  omissões, campos ambíguos e palavras-chave sem evidência. Aceita o formato antigo
  para compatibilidade. Somente espaços/quebras de linha são normalizados na comparação.
- Uma única correção automática, com prazo de 20 s; erros de provedor não são tratados
  como erro de evidência e não acionam esse retry. Nenhuma resposta inválida é salva.
- IA real, mesmo currículo fictício: passou na primeira chamada após a correção,
  sem leitura de PDF pessoal nem gravação de versão no teste direto do serviço.
- **163 testes backend passaram**, incluindo PostgreSQL descartável. Casos novos
  cobrem intervalos, keywords, retry limitado, timeout, cache e não persistência da resposta inválida.
- **12 testes de navegador passaram** com o build atualizado. Lint, TypeScript, build,
  Ruff e Bandit aprovados. Serviços reiniciados pela tarefa existente, sem mudar dados.
- O primeiro teste na API ainda atingiu um processo antigo. Ele foi identificado pelo
  comando/PID do projeto e encerrado; parar o supervisor sozinho não havia encerrado
  o backend destacado. Novo processo carregou a correção.
- Verificação final completa: PDF fictício em memória enviado à API com IA real,
  HTTP 200 e versão criada. A única versão sintética desse teste foi excluída usando
  sua identificação privada própria; nenhum currículo pessoal foi lido nesse diagnóstico.

## Busca manual pelo Telegram — 13/11/2026

- Atualização posterior: skill 1.3.0 instalada e cron existente atualizado com
  meta de 10 vagas compatíveis, ampliação de fontes e relato explícito de faltantes.
- 33 testes de bridge/automação passaram novamente, incluindo a contagem de
  faltantes no relatório e resumo. Rodada real às 17h21: 3 selecionadas, 1 nova,
  meta não atingida (7 faltantes), sem envio adicional ao Telegram.

- Usuário confirmou adaptação no site e recuperação do documento pelo Telegram.
- Helper ganhou `buscar`, exclusivo ao DM do dono; força nova coleta após o diário,
  sem outro aviso automático. Descoberta complementar usa um caminho fixo e lote atual.
- Skill instalada como 1.2.0, orientando diferenciar listar registros de pesquisar
  novas vagas, comunicar canais inacessíveis e não gerar currículo durante buscas.
- **33 testes de bridge/automação passaram**, com execução, rede e Telegram mockados;
  acesso fora do DM e falhas de subprocesso não expõem dados. Ruff aprovado.
