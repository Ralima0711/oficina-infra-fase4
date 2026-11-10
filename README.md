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

## Subir os três serviços junto com a infra

O `docker compose up -d` acima sobe só a infraestrutura. Para subir também os
três serviços e ver uma OS percorrer a saga de ponta a ponta:

```bash
docker compose --profile app up -d --build
docker compose --profile app ps
docker compose --profile app logs -f os-saga os-outbox
```

Isso exige os quatro repositórios como irmãos no disco, porque o compose constrói
a partir dos fontes:

```
Projetos/
├── oficina-infra-fase4        <- você está aqui
├── oficina-os-service
├── oficina-billing-service
└── oficina-execucao-service
```

| Container | Porta | O que é |
|---|---|---|
| `os-service` | http://localhost:8081 | API do OS |
| `os-saga` | — | consumidor da saga (`saga:consumir`) |
| `os-outbox` | — | publicador do outbox (`saga:publicar-outbox`) |
| `billing-service` | http://localhost:8082 | API do Billing |
| `billing-orcamento` | — | worker de `gerar-` e `anular-orcamento` |
| `billing-cobranca` | — | worker de `cobrar-` e `estornar-pagamento` |
| `execucao-service` | http://localhost:8083 | API da Execução |
| `execucao-worker` | — | consumidor da Execução |

**Oito containers de aplicação para três serviços**, e isso é de propósito: quem
consome fila não atende HTTP. É a mesma separação dos Deployments em `k8s/`, e
rodar com ela aqui é o que faz a demo bater com o cluster.

O Billing precisa do token de sandbox do Mercado Pago para fechar a cobrança.
Sem ele a stack sobe inteira e a saga vai até o pagamento:

```bash
MP_ACCESS_TOKEN='TEST-...' docker compose --profile app up -d
```

> Não coloque o token no `docker-compose.yml`. Ele entra por variável de
> ambiente ou por um `.env` ao lado do compose, que o `.gitignore` já cobre.

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
| `os.readmodel.eventos` | `os.*` — alimentaria a projeção CQRS do histórico, **sem consumidor nesta fase** |

O projetor do read model (ADR-0009) não existe ainda, e o OS Service publica
`os.cancelada` e `os.finalizada`, que casam com `os.*`. Fila ligada ao exchange
sem ninguém drenando cresce para sempre, e no limite de memória o RabbitMQ
**bloqueia os publicadores** — a saga dos três serviços para junto. Por isso ela
é limitada: `x-max-length` 10000 com `drop-head` e TTL de 24h. Quando o projetor
existir, é tirar o limite; até lá ela não derruba nada.

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
