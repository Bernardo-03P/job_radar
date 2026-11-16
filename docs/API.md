# API: contratos principais

Documentação interativa local: `http://127.0.0.1:8000/docs`.

## Vagas

| Método | Rota | Comportamento |
| --- | --- | --- |
| `GET` | `/health` | Disponibilidade básica da API |
| `GET` | `/api/v1/jobs` | Busca por `q`, paginação `limit`/`offset` |
| `POST` | `/api/v1/jobs` | Ingestão autenticada por `X-API-Key` de ingestão |

`matching_profile=true` filtra antes da paginação e deduplica recomendações sem apagar o histórico. `include_unconfirmed_hours=true` inclui vagas cujo único critério pendente é o horário; `schedule_status` separa `confirmed` de `unconfirmed`. Horário explicitamente incompatível não é exibido em nenhum grupo.

A URL é a identidade de ingestão. Parâmetros de rastreamento são normalizados sem apagar identificadores relevantes. Links compartilháveis Gupy válidos resolvem a URL canônica da mesma vaga.

## Currículos e fontes

| Método | Rota sob `/api/v1/resumes` | Comportamento |
| --- | --- | --- |
| `POST` | `/tailor` | Multipart `resume_file`, `job_description`, `job_id` opcional |
| `GET` | `/versions` | Lista histórico privado, com filtros e paginação |
| `GET` | `/versions/{id}` | Consulta uma versão autorizada |
| `GET` | `/versions/{id}/markdown` | Baixa Markdown da versão autorizada |
| `DELETE` | `/versions/{id}` | Exclui a versão autorizada |
| `POST` | `/sources` | Guarda um original opcional após ação explícita |
| `GET` | `/sources` | Lista metadados autorizados do cofre |
| `DELETE` | `/sources/{id}` | Remove o original autorizado |
| `POST` | `/tailor-saved` | Gera para um `source_id` e um `job_id`, com acesso administrativo |

O navegador utiliza `X-Resume-Token`. O helper administrativo utiliza `X-API-Key` com `RESUME_API_KEY`. Não use a chave de ingestão para ler currículos. Identificadores e tokens não devem ser expostos em URLs ou documentação pública.

O retorno de adaptação inclui `data`, `version` e `cached`. Os dados incluem `match_score`, `summary_of_changes`, `missing_critical_skills` e `adapted_resume_markdown`. Uma resposta em cache reutiliza a versão; não significa nova inferência.

## Limites e erros

- Upload: até 5 MiB; PDF com texto, até 100 páginas e 60 mil caracteres.
- Multipart interpretado em memória, com prazo e limite de concorrência.
- Parsing em subprocesso com limites de tempo, CPU e memória.
- Seleção JSON de fonte/vaga: um único item, corpo limitado e autenticação antes de processá-lo.
- Respostas privadas usam `Cache-Control: no-store`.
- `400`/`413`/`422`: formato ou limites inválidos; `401`/`404`: autorização/registro; `429`: limite temporário do provedor; `502`: resposta de IA inválida; `503`: provedor, banco ou recurso local indisponível.

A API não é um sistema multiusuário pronto para hospedagem pública. A exposição do código no GitHub não disponibiliza esses endpoints na internet.
