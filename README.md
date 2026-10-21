# oficina-infra-fase4

Infraestrutura compartilhada do Tech Challenge SOAT Fase 4 — Grupo 77.

## Stack de desenvolvimento

Tudo que os três microsserviços precisam, na sua máquina:

```bash
docker compose up -d
docker compose ps
```

| Serviço | Porta | Credenciais |
|---|---|---|
| RabbitMQ (AMQP) | 5672 | guest / guest |
| RabbitMQ (painel) | http://localhost:15672 | guest / guest |
| Postgres do OS Service | 5432 | os_service / os_service |
| MongoDB do OS Service (read model) | 27017 | — |
| Postgres do Billing | 5433 | billing_service / billing_service |
| Redis da Execução (fila) | 6379 | — |
| MongoDB da Execução (timeline) | 27018 | — |

Cada serviço tem o seu banco. **Nenhum acessa o banco de outro** — é regra do enunciado e do contrato.

## A topologia do RabbitMQ é versionada

As filas, exchanges e bindings vêm de `rabbitmq/definitions.json`, carregado no boot.
**Não crie fila pelo painel.** Se precisar de uma fila nova, ela entra no arquivo, vira PR,
e aí todo mundo sobe o ambiente igual.

### Filas de comando (point-to-point)

Um consumidor só. O orquestrador manda, o participante executa.

- `billing.gerar-orcamento`
- `billing.cobrar-pagamento`
- `billing.anular-orcamento` · compensação
- `billing.estornar-pagamento` · compensação
- `execucao.enviar-para-execucao`
- `execucao.cancelar-execucao` · compensação

### Eventos (publish-subscribe)

Exchange `oficina.eventos`, tipo `topic`.

| Fila | Recebe |
|---|---|
| `os.saga.eventos` | `orcamento.*`, `pagamento.*`, `execucao.*`, `aprovacao.*` — é o que o orquestrador escuta |
| `os.readmodel.eventos` | `os.*` — alimenta a projeção CQRS do histórico |

### O timeout de aprovação não é job agendado

`billing.aguardando-aprovacao` tem `x-message-ttl` de **7 dias** e nenhum consumidor.
Quando a mensagem expira, o RabbitMQ a encaminha sozinho para o exchange `oficina.espera`
com a routing key `aprovacao.expirada`, que cai em `billing.aprovacao-expirada`.

É o timeout do contrato v1.0 implementado pela própria mensageria — sem cron, sem job,
sem nada para esquecer de ligar em produção.

### Dead letter

Toda fila tem a sua `dlq.<nome>`, ligada ao exchange `oficina.dlx`. Mensagem que falha o
processamento vai para lá em vez de sumir — e a DLQ cheia é o primeiro lugar a olhar quando
a saga travar.

## Reset do ambiente

```bash
docker compose down -v   # apaga os volumes também
docker compose up -d
```

---

*Grupo 77 · FIAP SOAT Pós-Tech · Fase 4*
