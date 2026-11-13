# Validação — 12/11/2026

## Auditoria final local

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
