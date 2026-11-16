# Revisão antes de tornar o código público

Data: 16/11/2026. Escopo: árvore atual, histórico Git alcançável, execuções de CI e materiais de apresentação.

## Evidências da revisão

| Item | Resultado |
| --- | --- |
| Histórico inicial | Cinco commits; 169 conteúdos Git únicos examinados |
| Caminhos históricos | 178 versões de arquivos verificadas; sem documentos pessoais, bancos ou `.env` real versionados |
| Autoria dos commits | E-mails `users.noreply.github.com` |
| CI anterior à publicação | Cinco execuções; 46 arquivos de log examinados |
| Artefatos e releases existentes | Nenhum |
| Issues existentes | Nenhuma |
| Credenciais | Sem correspondências com as chaves/tokens locais ou com os padrões verificados |
| Identificadores privados de currículo | Sem correspondências no histórico e nos logs examinados |
| Captura pública | Dados fictícios e resposta simulada; nenhum backend pessoal ou provedor acessado |

Os valores privados usados na comparação não foram incluídos em relatórios, argumentos públicos ou arquivos versionados. Arquivos locais de auditoria permanecem em `.runtime`, ignorado pelo Git.

## Controles mantidos

- `.env`, PDFs, documentos, bancos, cofre e relatórios locais ficam fora do Git.
- `.env.example` contém apenas exemplos e campos vazios de configuração. Credenciais de PostgreSQL no ambiente de desenvolvimento são exemplos locais, não chaves de provedor.
- A imagem da documentação utiliza empresas e candidato fictícios, identificados como demonstração.
- `scripts/check_publish.py --history` passa a verificar todos os refs e versões alcançáveis. O CI busca o histórico completo antes dessa verificação.
- Uma regressão automatizada confirma que um segredo sintético já removido ainda é detectado no histórico e que seu valor não é impresso.
- O modo de demonstração da instalação inclui os dois grupos de horário e não utiliza inferência.

Esta revisão registra o que foi examinado e não é uma garantia de ausência absoluta de segredos ou falhas. Novos commits e materiais precisam continuar seguindo os mesmos controles.

## Publicação e operação

Tornar o repositório público disponibiliza código, histórico e CI. A aplicação, banco, bot, cofre e documentos permanecem no ambiente local do operador. Esta publicação não altera tokens, não liga os serviços pessoais e não publica uma instância do site.
