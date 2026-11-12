# Observabilidade da saga — Fase 4

**Grupo 77 · um dashboard para os três serviços, versionado aqui**

O que o vídeo precisa mostrar é **um trace atravessando OS, Billing e Execução**. Em três
dashboards separados isso não aparece: cada um mostraria o seu pedaço. Por isso há **um
dashboard só**, e o painel de cada serviço é uma **página** dentro dele. Mesma regra do
`rabbitmq/definitions.json`: fonte única no infra, nenhum serviço mantém o seu.

O contrato que os dashboards usam é o [`docs/contrato-observabilidade.md`](../docs/contrato-observabilidade.md)
(`service.name`, `trace.id`, `saga.id`, spans `<destino> publish` / `<origem> process`).

## Arquivos

| Arquivo | O que é |
|---|---|
| `dashboard-saga.json` | O dashboard, no formato de exportação do New Relic |
| `alertas-saga.json` | As condições NRQL do alerta de falha no processamento de OS |
| `test_dashboard.py` | Confere o JSON (páginas, grade, serviços citados). `python3 -m unittest discover -s observabilidade` |

## Páginas

| Página | Para quê |
|---|---|
| **Visão geral — trace ponta a ponta** | Traces recentes com os serviços que cada um atravessou, spans e erros por serviço, mensagens da saga, latência publish → process, falhas e DLQ |
| **OS Service** · **Billing Service** | Spans e latência de mensageria, erros, mensagens processadas e logs de erro, filtrados pelo `service.name` do serviço |
| **Execução Service** | O mesmo, mais: fila por prioridade, eventos publicados, `execucao.falhou`, compensações por resultado, DLQ, tempo por status e idempotência |

## Alerta

`alertas-saga.json` tem quatro condições (`count(*) > 0` em 5 min): `execucao.falhou` publicado,
falha ao processar mensagem, mensagem na DLQ e span com erro em qualquer serviço da saga.
**Ainda não aplicado**: pode virar `newrelic_nrql_alert_condition` no Terraform do
`oficina-infra-k8s` (que já tem policy, canal de e-mail e workflow) ou ser criado por NerdGraph.

## Como importar

No New Relic: **Dashboards → Import dashboard**, colar o `dashboard-saga.json` e escolher a conta.
As queries trazem `accountIds` vazio de propósito: a conta não é segredo, mas muda entre o lab e
o ambiente pessoal.

## O que não está verificado

- **Nomes dos atributos de log.** As queries usam `evento`, `resultado`, `fila.prioridade`,
  `os.status_anterior` e `messaging.destination.name` no nível raiz do log, como o dashboard da
  Fase 3 já faz com `os.status_anterior`. Conferir no New Relic (Logs → um log do
  `oficina-execucao-service`) se não ficam sob `context.`; se ficarem, é uma troca de prefixo.
- **OS e Billing ainda não exportam nada para este dashboard** (conferido em 12/11, `main` do
  `oficina-os-service` em `1d0b56b` e do `oficina-billing-service` em `2f62f74`): nenhum dos dois
  tem o SDK do OpenTelemetry, só repassam o `traceparent` no envelope. Sem span deles, o trace no
  New Relic tem só os spans da Execução, e a visão geral não mostra os três serviços. Os logs
  deles são texto livre no canal `stack`, sem `service.name` nem `trace.id`. As páginas do OS e do
  Billing ficam vazias até cada serviço adotar a seção 4 do `contrato-observabilidade.md`
  (copiar os arquivos de tracing e o canal `stdout_json`). Os widgets específicos (orçamento,
  pagamento, `os.cancelada`) entram depois disso, com os nomes de log que cada um escolher.
- **Dado real:** nada disto foi visto com tráfego. Precisa dos serviços exportando OTLP para o New
  Relic (`OTEL_EXPORTER_OTLP_*`).
