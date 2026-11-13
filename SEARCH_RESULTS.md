# Rodada de busca — 13/11/2026

Perfil: estágio prioritário, trainee complementar, Dados/IA, Desenvolvimento de Sistemas
e Suporte N1, com as restrições geográficas de `agent/search_profile.json`.

## Coleta automática

RD Station: quatro vagas recebidas, nenhuma no nível solicitado. Starian: um estágio
remoto em suporte validado e atualizado no banco, mantendo o ID 13. Nenhuma vaga nova
foi inserida nessa repetição.

## Descoberta complementar

LinkedIn, Indeed e InfoJobs foram pesquisados nesta rodada. Os itens abaixo são
candidatos a revisão, não foram importados automaticamente nem receberam currículo.
A disponibilidade e os requisitos podem mudar após a consulta.

| Canal | Anúncio | Avaliação inicial |
| --- | --- | --- |
| LinkedIn | [Veeries — Estagiário de TI Phyton](https://br.linkedin.com/jobs/view/estagi%C3%A1rio-de-ti-phyton-at-veeries-4481474004) | Dados/ETL e suporte; presencial na SC-401, JCK Business Hall; exige estar a partir do segundo ano. Conferir candidatura e curso. |
| LinkedIn | [Concert — Estágio em IA e Full Stack](https://br.linkedin.com/jobs/view/025-2026-lab-est%C3%A1gio-%E2%80%94-intelig%C3%AAncia-artificial-e-desenvolvimento-full-stack-at-concert-technologies-4480590677) | Anuncia remoto, seis horas/dia; pede Angular/Git e pelo menos um ano restante de curso. Confirmar aceitação de residentes de Florianópolis. |
| Indeed | [ACATE — Estágio em operação e dados](https://br.indeed.com/viewjob?jk=56699c3294206b3c) | Dados, dashboards e processos; Florianópolis. Endereço/modalidade e candidatura atual precisam ser confirmados no recrutamento original. |
| InfoJobs | [Polinfo — Estagio Area De TI](https://www.infojobs.com.br/vaga-de-estagio-area-ti-em-santa-catarina__12050295.aspx) | Suporte presencial; anúncio menciona Avenida Patrício Caldeira de Andrade. Bairro não validado, portanto não aprovado para importação. |
| Sólides | [Sambatech — Estágio em IA Aplicada](https://vagas.solides.com.br/vaga/881983) | Anuncia 100% remoto e atividades com LLM/RAG. Confirmar elegibilidade geográfica e curso antes de importar. |

## Resultados que não foram aprovados

- [BeFly — Estágio de Suporte](https://befly.gupy.io/jobs/12666454): a página original
  exibe "Applications closed", apesar de agregadores ainda anunciarem disponibilidade.
- [Geopixel — Banco de Dados](https://geopixel.gupy.io/jobs/12775883): indícios divergentes
  entre agregadores e descrição; integração exploratória não produziu registro
  verificável. Não importado nem adicionado às fontes automáticas.
- Instituto Cordial: banco de talentos para oportunidade futura, com reuniões presenciais
  esporádicas em São Paulo; não é uma vaga remota plenamente compatível com o perfil.
- SiDi: anúncio de Dados/IA com atuação presencial no Recife; excluído pela localização.

## Atualização após a rodada automatizada

O Hermes validou o [Programa de Estágio Tech.AI 2027 da Blip](https://estagio.blip.ai/)
na página original e importou o ID 14, mantendo Starian ID 13 sem duplicação.
Telegram confirmou o resumo. Inscrições Blip: 04/11 a 30/11/2026, 100% remoto;
confira curso e período de graduação no edital antes de se candidatar. Nenhum
currículo ou candidatura foi enviado.

## Estado final do produto

### Ampliação automática às 17h36 de 13/11/2026

Nove fontes responderam sem falhas. Quatro vagas compatíveis foram validadas,
com seis faltantes para a meta; uma nova: Geopixel ID 16, estágio com ênfase em
Banco de Dados, https://geopixel.gupy.io/jobs/12775883. O estado público original
informa modalidade remota, país Brasil e candidatura publicada, com requisitos
de QGIS, SQL, Python e dados geográficos. O escritório citado fica em São José
dos Campos; a modalidade estruturada da vaga é remota. Confira os requisitos
específicos antes de escolher uma candidatura.

Leega trainee e IEL 32327 ficaram para revisão de elegibilidade/localização.
IEL 31422 foi confirmado encerrado/não encontrado e excluído. As vagas existentes
foram reutilizadas sem duplicação. Nenhuma candidatura, currículo ou mensagem
adicional de Telegram foi enviada nesta rodada.

### Verificação adicional em 13/11/2026, 17h21 (São Paulo)

Meta configurada: 10 anúncios distintos compatíveis por rodada; não significa
10 anúncios novos nem garantia de disponibilidade. Ampliadas as orientações de
descoberta para IEL/SC, CIEE/SC e Super Estágios, com até 20 consultas úteis.
O relatório registra `minimum_results`, `meets_target` e `shortfall`.

Rodada real com páginas originais reconsultadas: **3 vagas selecionadas, 1 nova,
faltam 7 para a meta**. Blip e Starian preservadas; incluído ID 15, estágio ADS
da EVOLUA, via IEL/SC, presencial na Trindade. A página original exibe candidatura
por login; publicação não informada. Atividades incluem apoio a programação e
robótica educacional, sem exigência de experiência profissional.

Esta verificação usou `--no-notify`: não enviou outro resumo automático.
O campo `notification_status=sent` preserva o envio anterior do dia.
Anúncios sem bairro confirmado, elegibilidade remota clara ou abertura verificável
continuam fora da contagem. A data de checagem não é a data de publicação.

- Ampliar a descoberta recorrente nas plataformas preferidas, respeitando acesso público.
- Execução às 9h nos dias úteis, recuperação no login e deduplicação implementadas.
- Avisos privados e geração pelo bot somente para vagas escolhidas implementados.
- Limpeza/otimização, revisão técnica e testes adversos concluídos, com evidências em
  AUDIT.md e VALIDATION.md. Cobertura de plataformas depende do acesso público.
