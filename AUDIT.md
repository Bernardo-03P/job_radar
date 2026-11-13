# Auditoria técnica — job_radar

Auditoria local em 12/11/2026. Duas rodadas: revisão da implementação e testes
adversos. Os resultados não garantem ausência absoluta de falhas. Uso previsto: local.

## Rodada 1 — correções

| ID | Achado | Correção |
| --- | --- | --- |
| A01 | Geração sem identificação | X-Resume-Token obrigatório antes da leitura multipart |
| A02 | Multipart sem isolamento suficiente | Parser incremental BytesIO; limites por campo, prazo e concorrência |
| A03 | Gerações duplicadas | Cache e lock por chave; advisory lock PostgreSQL entre processos |
| A04 | Transação aberta na inferência | Rollback antes da chamada; lock em conexão autocommit |
| A05 | Exceções expunham detalhes | JSON genérico 500/503, com CORS |
| A06 | Chave Unicode causava exceção | Comparação constante em bytes |
| A07 | PDF nativo executado no servidor | Subprocesso com limites de memória/CPU e timeout |
| A08 | Oito avisos npm de minimatch | Override específico; npm audit sem vulnerabilidades conhecidas |
| A09 | pip vulnerável e dependências sem lock | pip atualizado; locks universais com hashes e separação de dev |
| A10 | Git herdado da pasta pessoal | Repositório isolado e scanner do índice |
| A11 | Histórico atrasado e cache incorreto | Revisões de mutação, IDs de versões, validação de respostas e paginação |
| A12 | Cron duplicado e API com destino aberto | Registro idempotente, estado inválido rejeitado, URL loopback |
| A13 | Banco sem migrações | Alembic adota tabelas anteriores; inicialização serializada |
| A14 | Shell incompatível com Hermes | Exemplos bash/PowerShell e comando /job_radar |

## Rodada 2 — evidências

- 81 testes backend passaram, incluindo PostgreSQL descartável com pgvector.
- Multipart truncado, duplicado, tamanho falso, limites, concorrência e timeout.
- Hypothesis: 200 exemplos aleatórios, com fechamento dos buffers.
- Cancelamento e deduplicação; bloqueio PostgreSQL e liberação entre conexões.
- Migrações concorrentes e preservação de registros sintéticos anteriores.
- Falhas de banco/aplicação, Unicode, autenticação e isolamento do histórico.
- Timeout de PDF encerra e aguarda worker; PDFs inválidos/sem texto rejeitados.
- Navegador: resposta inválida, histórico atrasado, exclusão de versão antiga da
  mesma vaga, paginação acima de cem versões e interações usuais.
- Ruff e Bandit (médio/alto) passaram; subprocessos usam executáveis resolvidos,
  argumentos separados e nenhum shell. Alertas baixos foram revisados.
- pip-audit e npm audit: nenhuma vulnerabilidade conhecida encontrada.
- IA e Telegram mockados; nenhum custo de inferência nos testes.

## Privacidade e publicação

Documentos de teste são sintéticos. Em 12/11 o original não era persistido; em 13/11
foi acrescentado o cofre opcional DPAPI, separado do banco e fora do Git. O texto adaptado
fica no banco local por consentimento. A política do provedor se aplica ao envio à IA.
O scanner do índice procura padrões de chaves, segredos do .env e documentos/bancos;
não é um detector universal. .env, currículos pessoais e banco ficam fora do Git.
Destino autorizado: repositório privado Bernardo-03P/job_radar.

## Limites e próximas etapas

- Primeira coleta real validada em 13/11/2026: dez vagas do Grupo QuintoAndar,
  importadas sem duplicatas na repetição. As duas demonstrações anteriores foram preservadas.
- Perfil atualizado: estágio/trainee em Dados/IA, Sistemas e Suporte, N1 prioritário;
  localidade na ilha de Florianópolis ou remoto elegível no Brasil. A lista recomendada
  exclui os registros anteriores incompatíveis sem apagá-los. Primeiro estágio remoto
  de suporte da Starian validado; o anúncio não informa N1/N2. Fontes iniciais, sem
  cobertura exaustiva. Endereços e restrições incertos seguem para revisão manual.
- Busca às 9h em dias úteis com recuperação no login Windows implementada em 13/11.
- Criação pelo Telegram e original opcional protegido implementados em 13/11.
- A geração continuará somente para vagas escolhidas.
- Modo conservador preserva trechos; sem reescrita STAR livre nem garantia ATS.
- A baseline confere nomes de colunas; não repara esquemas alterados manualmente.
  Faça backup antes de atualizar o banco.
- Exposição pública exige autenticação, HTTPS, limites distribuídos e operação próprios.
- O lock entre processos ocupa uma conexão durante a inferência; dimensione o pool
  antes de aumentar o volume. O limite de uploads vale por processo.
- CI e dependências precisam de acompanhamento contínuo.

## Atualização final — 13/11/2026: duas rodadas

### Rodada 1 — revisão, limpeza e correções

- Cron existente atualizado, sem outro job/bot/provedor. Catch-up ativo, horário
  São Paulo, entrega local do Hermes e resumo privado pelo script.
- Supervisor na tarefa `JobRadar-Local-Startup`, mesma conta Windows, sem elevação
  permanente. Executáveis resolvidos sem depender do PATH do terminal.
- Locks de processo e estado diário durável; até três recuperações, espaçadas por
  uma hora. Prazo do CLI Hermes ajustado ao disparo síncrono, sem encerrar uma busca
  normal em 30 segundos. Contingência determinística sem geração de currículo.
- Aviso somente ao ID fixo na allowlist exata do bot. Resposta ambígua não provoca
  reenvio automático. Estado de ingestão parcial é preservado para recuperação.
- Cofre opcional DPAPI CurrentUser, gravação atômica, um original por navegador,
  exclusão separada das versões e ausência de endpoint para baixar o original.
- Geração exige vaga e fonte; helper exige DM do dono e pedido explícito. Usa o
  mesmo fluxo de evidências/cache do site. Não há geração em lote ou durante buscas.
- Autenticação antes de ler JSON da seleção, limite 4 KiB, prazo e concorrência.
- Tracking removido das URLs sem remover o identificador da vaga; menos duplicatas.
- JSON do CLI em ASCII escapado evita erro Unicode no console Windows.
- Scanner ampliado aos arquivos novos não ignorados, sem alterar o índice Git.

### Rodada 2 — testes adversos e evidências

- **151 testes backend passaram**, incluindo PostgreSQL descartável/pgvector,
  migrações, locks entre conexões e proteção DPAPI real com dados sintéticos.
- Seleção sem autenticação, corpo excessivo/chunked, lote rejeitado, fonte de outro
  navegador, ID ausente, tampering, cache, exclusão e preservação do histórico.
- São Paulo, fim de semana, última ocorrência perdida, concorrência, estado corrompido,
  ingestão parcial, contingência e aviso ambíguo sem reenvio.
- **12 testes de navegador passaram**: opt-in, consulta após reload, exclusão sem IA
  e seleção de vaga com API pessoal real.
- Ruff, Bandit médio/alto, ESLint, TypeScript e build aprovados. pip-audit e npm audit
  não encontraram vulnerabilidades conhecidas. Scanner do worktree aprovado.
- Supervisor observado Running; backend persistiu após encerrar o lançador.
  Recuperação retornou `already_completed`, sem segundo aviso.
- Hermes real: rodada concluída, Blip ID 14 novo, Starian ID 13 reutilizado,
  Telegram confirmou o resumo. Bloqueios de canais públicos foram relatados pelo agente.
  Um disparo manual adicional falhou no runtime Hermes; estado concluído e aviso
  confirmado foram preservados. Esse disparo não foi declarado bem-sucedido.

### Limites da verificação

O PC não foi reiniciado fisicamente; foram testados reinício da tarefa, persistência
dos serviços e cálculos de recuperação. A adaptação de currículo e documentos Telegram
usam mocks nos testes: nenhum currículo pessoal foi gerado/enviado automaticamente.
A pesquisa real usa o provedor/cota Hermes já configurados pelo dono. Sites podem
bloquear acesso público; não há busca exaustiva ou contorno de autenticação. Vagas podem
fechar depois; ausências ainda não são arquivadas automaticamente. O cofre requer a
mesma conta Windows e não protege contra malware que já controle essa conta. Limpar os
dados do navegador perde sua identificação; o acesso administrativo do bot permanece privado.
Estas verificações não garantem ausência absoluta de falhas.
