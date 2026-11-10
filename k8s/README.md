# Manifestos Kubernetes — Fase 4

**Grupo 77 · namespace único `oficina`**

Entregável explícito do enunciado (*"Dockerfile e manifestos Kubernetes"*). Na Fase 3
o job de deploy nunca chegou a aplicar nada — não havia `KUBECONFIG` cadastrado e o
pipeline caía no ramo de Minikube em 4 segundos. Esta pasta é o que o pipeline passa
a aplicar.

---

## Estrutura

```
base/                 namespace, RabbitMQ e Kong — sobe primeiro, todo mundo depende
os-service/           Postgres + Mongo + API + orquestrador + projetor + HPA
billing-service/      Postgres + API + worker + HPA
execucao-service/     Redis + Mongo + API + worker + HPA
scripts/              geradores e conferência
```

O número no nome do arquivo é a ordem de aplicação: `00` namespace, `10` broker,
`20` bancos, `30` configuração, `40` aplicação, `50` autoscaling.

Os bancos ficam **dentro da pasta de cada serviço**, não numa pasta `bancos/`
comum. Isso não é organização: é o ADR-0007 escrito no sistema de arquivos. Cada
serviço sobe o banco dele e ninguém mais tem credencial para esse banco.

---

## Ordem de aplicação

```bash
kubectl apply -f base/
# espere o RabbitMQ ficar Ready antes de subir os workers —
# consumidor que sobe antes do broker entra em CrashLoopBackOff
kubectl -n oficina rollout status statefulset/rabbitmq

kubectl apply -f os-service/
kubectl apply -f billing-service/
kubectl apply -f execucao-service/
```

---

## Secrets — o que **não** está neste repositório

Nenhum valor de credencial está versionado aqui. Os manifestos referenciam Secrets
por nome; os Secrets se criam uma vez por cluster. Depois de cada recriação do lab,
tudo isso se perde junto com o cluster e precisa ser recriado.

| Secret | Chaves | Usado por |
|---|---|---|
| `rabbitmq-credentials` | `username`, `password` | todos os serviços e o broker |
| `os-postgres-credentials` | `username`, `password` | OS Service |
| `os-mongo-credentials` | `username`, `password` | OS Service |
| `os-jwt` | `public-key` | OS Service (guard `cliente`, ADR-0004/0005 da Fase 3) |
| `billing-postgres-credentials` | `username`, `password` | Billing |
| `billing-mercadopago` | `access-token` | Billing (sandbox) |
| `execucao-redis-credentials` | `password` | Execução |
| `execucao-mongo-credentials` | `username`, `password` | Execução |
| `observabilidade` | `new-relic-license-key` | todos os serviços |

O formato do comando, para quem for criar:

```bash
kubectl -n oficina create secret generic os-postgres-credentials \
  --from-literal=username='...' \
  --from-literal=password='...'
```

A chave pública do JWT vem de arquivo, não de literal:

```bash
kubectl -n oficina create secret generic os-jwt --from-file=public-key=jwt-public.pem
```

> Secret não entra em commit, não entra em print e não entra em mensagem de grupo.
> Se um valor desses vazar num canal qualquer, ele tem que ser rotacionado — não
> basta apagar a mensagem.

---

## Três coisas que o dono de cada serviço precisa confirmar

Estes manifestos assumem três convenções. Se o serviço não seguir, o pod sobe e
morre, e o erro é chato de achar.

Três convenções dependem do Dockerfile e das rotas de cada serviço. Se alguma não
bater, o pod sobe e morre, e o erro é chato de achar.

| Serviço | Porta | Probe | Worker | Conferido por |
|---|---|---|---|---|
| **OS** | 8080 ✓ | `/up` ✓ | `saga:consumir` · `saga:publicar-outbox` ✓ | Roberta, 09/11 |
| **Billing** | 8080 ✓ | `/api/health` ✓ | `fila:consumir --fila=…` ✓ | Gustavo, 04/11 · Roberta, 09/11 |
| **Execução** | 8080 ✓ | `/health` ✓ | `execucao:consumir` ✓ | David, 02/11 |

**Essa conferência já pagou duas vezes.**

Na Execução, o manifesto dizia `fila:consumir` e o comando real é `execucao:consumir`
— o pod subiria e morreria. Na mesma passada apareceu que faltava criar os índices do
Mongo, que o `docker-compose` do serviço faz na subida e os manifestos não faziam;
virou `initContainer` na API e no worker.

No Billing, dois erros meus: a probe chamava `GET /health`, que responde **404** porque
no Laravel a rota vive sob o prefixo `/api`; e o token do Mercado Pago entrava como
`MERCADOPAGO_ACCESS_TOKEN`, enquanto o `config/services.php` do serviço lê
`MP_ACCESS_TOKEN`. Os dois foram corrigidos.

O OS Service foi conferido em 09/11, depois que a saga entrou na `main`: o
`bootstrap/app.php` declara `health: '/up'`, e os dois workers são
`saga:consumir` (eventos) e `saga:publicar-outbox` (publicação do outbox), em
Deployments separados. O `saga:consumir-execucao`, que cobria só o passo 4,
deixou de existir.

**O Billing agora tem dois workers, um por fila.** O acompanhamento do pagamento
faz polling no gateway dentro do callback do consumidor, e com os padrões
(`poll_interval_seconds` 30, `poll_max_attempts` 20) o pior caso são dez minutos
segurando a mensagem. Como o prefetch é 1, num processo só isso segurava a fila
de `gerar-orcamento` atrás da cobrança. Não travava a saga — o `consultar()`
desiste no teto e publica `pagamento.recusado` com motivo `timeout` — mas é
*head-of-line blocking*: a fila de orçamento esperava por uma coisa que não tem
nada a ver com ela. Em produção é capacidade; na demo parece travamento.

Para isso o `fila:consumir` ganhou a opção `--fila`, e cada Deployment roda a
sua. Sem a opção o comportamento é o de antes, um processo para as duas.

---

## Por que worker é Deployment separado da API

Quem consome fila não atende HTTP. Se o consumidor rodasse no mesmo pod da API,
o HPA escalaria o orquestrador da saga por CPU de requisição web — o avanço da
saga ficaria amarrado ao tráfego do site, que não tem relação nenhuma com ele.

No OS Service são **dois** workers, não um:

- `os-service-saga` consome `os.saga.eventos` e avança ou compensa a saga
- `os-service-projector` consome `os.readmodel.eventos` e escreve o read model no Mongo

Separados porque toleram falha de forma diferente. Projeção travada deixa o
histórico atrasado — que o ADR-0009 já assume como consistência eventual. No mesmo
processo, um erro de projeção pararia a saga.

Os workers ficam em **2 réplicas fixas**, sem HPA: o consumidor é idempotente pelo
`messageId` (contrato v1.0, Parte 5), então duas instâncias na mesma fila é seguro.
Escalar por profundidade de fila exigiria KEDA, que está fora do escopo.

---

## HPA

Mínimo 2 / máximo 10, CPU 70% ou memória 80% — herdado do ADR-0002, que a Fase 2
já validou com teste de carga no k6. No OS Service o mínimo de 2 não é só
elasticidade: é a mitigação do ponto único de falha registrada no ADR-0008.

---

## Topologia do RabbitMQ: uma fonte, dois destinos

A topologia vive em **um lugar só**, `rabbitmq/definitions.json` no
`oficina-infra-fase4`. O `docker-compose` monta o arquivo direto; o cluster precisa
dele dentro de um ConfigMap. `base/11-rabbitmq-definitions.yaml` é **gerado**, não
editado à mão:

```bash
python3 scripts/gera-configmap-definitions.py > base/11-rabbitmq-definitions.yaml
```

E os nomes de fila dos ConfigMaps se conferem contra ela:

```bash
python3 scripts/confere-filas.py
```

Esse segundo script pega o erro mais silencioso que esta arquitetura permite: fila
com nome digitado errado. O serviço sobe, conecta, declara a fila errada e fica
consumindo uma fila que ninguém publica. A saga para no meio sem log de erro.
Vale rodar no pipeline.

A única fila do broker sem consumidor é `billing.aguardando-aprovacao`, e isso é
proposital: é a sala de espera onde a mensagem fica parada até o TTL de 7 dias
vencer e o dead-letter mandá-la para `billing.aprovacao-expirada` (ADR-0010).

---

## Validação

```bash
kubeconform -summary -strict -kubernetes-version 1.30.0 \
  base os-service billing-service execucao-service
```

Estado atual: **32 recursos em 21 arquivos, 0 inválidos.**

---

## O que ainda não está aqui

| Falta | Observação |
|---|---|
| **Rotas do OS Service no Kong** | Os três prefixos do bloco `os-service` em `base/20-kong.yaml` estão marcados **A CONFIRMAR**: vieram da API da Fase 3 e o serviço novo ainda não existe. Quando existir, é conferir, não inventar. |
| **Migrations na subida** | Os bancos relacionais sobem vazios. A Execução já resolveu os índices do Mongo com `initContainer`; falta a mesma decisão para as migrations do Postgres do OS e do Billing. |

---

## Kong — o ponto único de entrada

`base/20-kong.yaml`, modo **DB-less**: a configuração inteira vive no ConfigMap,
versionada. Rota não se cria pelo Admin API — mesma regra das filas do RabbitMQ.

| Prefixo | Vai para | Origem |
|---|---|---|
| `/api/ordens-servico`, `/api/clientes`, `/api/veiculos` | OS Service | **a confirmar** |
| `/api/public/ordens-servico` | OS Service, com **JWT RS256** | **a confirmar** |
| `/api/orcamentos`, `/api/pagamentos` | Billing | `routes/api.php` |
| `/api/execucao` | Execução | `routes/api.php` |

O token do cliente é o mesmo RS256 da Fase 3 (ADR-0004/0005): a Lambda assina com
a privada, o Kong valida com a pública. A chave pública entra por variável de
ambiente a partir do Secret `os-jwt` — não está no ConfigMap. O guard da aplicação
continua valendo: o Kong barra token inválido antes de chegar no serviço, e o
serviço ainda confere o escopo por CPF.

**O Admin API escuta só em `127.0.0.1`.** Kong com Admin API exposto é uma porta
aberta para reconfigurar o gateway de fora, e em DB-less ele nem precisa existir
para operar.

O endereço público sai de `kubectl -n oficina get svc kong-proxy`.

---

*Grupo 77 · FIAP SOAT Pós-Tech · Fase 4*
