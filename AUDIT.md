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

Documentos de teste são sintéticos. PDF original não é persistido. O texto adaptado
fica no banco local por consentimento. A política do provedor se aplica ao envio à IA.
O scanner do índice procura padrões de chaves, segredos do .env e documentos/bancos;
não é um detector universal. .env, currículos pessoais e banco ficam fora do Git.
Destino autorizado: repositório privado Bernardo-03P/job_radar.

## Limites e próximas etapas

- Coleta real ainda não validada; vagas atuais são demonstrações.
- Busca diária às 9h com recuperação ao ligar o PC ainda não implementada.
- Criação pelo Telegram e armazenamento separado do original ainda não implementados.
- A geração continuará somente para vagas escolhidas.
- Modo conservador preserva trechos; sem reescrita STAR livre nem garantia ATS.
- A baseline confere nomes de colunas; não repara esquemas alterados manualmente.
  Faça backup antes de atualizar o banco.
- Exposição pública exige autenticação, HTTPS, limites distribuídos e operação próprios.
- O lock entre processos ocupa uma conexão durante a inferência; dimensione o pool
  antes de aumentar o volume. O limite de uploads vale por processo.
- CI e dependências precisam de acompanhamento contínuo.
