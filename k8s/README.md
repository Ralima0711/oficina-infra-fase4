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
os-service/           Postgres + API + orquestrador + publicador do outbox + HPA
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
| `os-app-key` | `app-key` | OS Service (API e os dois workers) |
| `os-jwt` | `public-key` | **Kong**, para validar o RS256 (ADR-0004/0005 da Fase 3) |
| `billing-app-key` | `app-key` | Billing (API e os dois workers) |
| `billing-postgres-credentials` | `username`, `password` | Billing |
| `billing-mercadopago` | `access-token` | Billing (sandbox) |
| `execucao-app-key` | `app-key` | Execução (API e worker) |
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

As três `app-key` se geram com o próprio artisan, uma por serviço — não se
reaproveita a mesma chave em dois serviços, pelo mesmo motivo de não se
reaproveitar senha de banco:

```bash
for s in os billing execucao; do
  kubectl -n oficina create secret generic "${s}-app-key" \
    --from-literal=app-key="$(docker run --rm php:8.4-cli php -r \
      'echo "base64:".base64_encode(random_bytes(32));')"
done
```

> Nenhum manifesto definia `APP_KEY` até 10/11. O Laravel sobe sem ela e só
> estoura `MissingAppKeyException` quando alguma coisa toca o encrypter — a API
> responde 500 e o worker morre no meio do consumo. Era o tipo de falha que só
> aparece no cluster, porque na máquina o `.env` tem a chave.

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

No OS Service são **dois** workers, e eles não são duas cópias da mesma coisa:
um só lê do broker e o outro só escreve nele.

| Deployment | Comando | O que faz | Réplicas |
|---|---|---|---|
| `os-service-saga` | `saga:consumir` | consome `os.saga.eventos` e avança ou compensa a saga | 2 |
| `os-service-outbox` | `saga:publicar-outbox` | publica no RabbitMQ o que a saga gravou no outbox | **1** |

O orquestrador não publica nada: toda saída da saga vai para a tabela
`saga_outbox` dentro da mesma transação que muda o estado da OS, e sai depois
pelo publicador. **Sem o `os-service-outbox` a saga grava a intenção e nunca
publica** — nenhum comando chega ao Billing e a saga para no primeiro passo, sem
erro em log nenhum. Esse Deployment faltava até 10/11.

O consumidor fica em **2 réplicas fixas**, sem HPA: ele é idempotente pelo
`messageId` (contrato v1.1, Parte 5, regra 1), então duas instâncias na mesma fila
é seguro. Escalar por profundidade de fila exigiria KEDA, fora do escopo.

O publicador fica em **1 réplica, e isso é uma restrição do código, não uma
escolha de capacidade**: `OutboxPublisher::publicarPendentes()` seleciona as
linhas pendentes sem travar linha nenhuma — não há `FOR UPDATE SKIP LOCKED`. Com
duas réplicas, as duas leem o mesmo lote e publicam a mesma mensagem antes de
qualquer uma marcar `publicado_em`. Não quebra, porque o consumidor descarta
`messageId` repetido, mas é tráfego duplicado de graça. Quem quiser escalar o
publicador mexe no `SELECT` primeiro; subir réplica antes disso é só duplicar
mensagem.

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

Duas filas do broker não têm consumidor, por motivos diferentes, e as duas estão
na lista de exceções do `confere-filas.py` com o motivo escrito ao lado:

- `billing.aguardando-aprovacao` é a sala de espera do ADR-0010: a mensagem fica
  parada até o TTL de 7 dias vencer e o dead-letter mandá-la para
  `billing.aprovacao-expirada`. Consumidor nela quebraria o timeout.
- `os.readmodel.eventos` esperava o projetor do read model, que não existe nesta
  fase. Como o OS publica `os.cancelada` e `os.finalizada` e os dois casam com o
  binding `os.*`, ela recebia mensagem e ninguém drenava. Fila assim cresce para
  sempre e, no limite de memória, o RabbitMQ **bloqueia os publicadores** — a
  saga dos três serviços pararia junto, e o sintoma não aponta para cá. Virou
  ring buffer: `x-max-length` 10000, `x-overflow: drop-head`, TTL de 24h. A DLQ
  dela saiu, porque já não há dead-letter para mandar para lá.

A lista de exceções exige motivo por fila de propósito. Check vermelho crônico
todo mundo aprende a ignorar, e aí ele deixa de pegar o erro de verdade.

---

## As extensões do PHP que cada imagem precisa

Os três serviços são Laravel sobre a imagem oficial do PHP, e a imagem oficial
vem enxuta. O que **falta** não aparece ao rodar na máquina (o PHP do
desenvolvedor já tem tudo) e também não aparece como erro de runtime: aparece
como o `composer install` do build falhando na checagem de plataforma.

| Serviço | php-amqplib | Exige | Estado |
|---|---|---|---|
| **OS** | `v2.8.0` | `ext-bcmath` | adicionada em 10/11 — o Dockerfile não existia |
| **Billing** | `v3.7.5` | `ext-sockets` | adicionada em 10/11 — **o build não concluía** |
| **Execução** | `v3.7.5` | `ext-sockets`, `ext-mongodb` | já estava certo |

As duas versões de `php-amqplib` são uma divergência de verdade: o OS está no
`^2.8` e os outros dois no `^3.7`, e é por isso que as extensões exigidas
diferem — a 2.8 pede `bcmath`, a 3.7 pede `sockets`. Não é urgente, mas vale
alinhar na próxima fase em vez de descobrir de novo.

Além dessas, `pcntl` entrou no OS e no Billing. Os dois registram `SIGTERM` para
terminar a mensagem em curso antes de sair, mas o código está guardado por
`function_exists()` — sem a extensão ele não quebra, simplesmente não faz nada, e
o `rollout` do Kubernetes corta o worker no meio do ACK. Era um encerramento
gracioso escrito e inerte.

E os dois ganharam `.dockerignore`, que também não existia: sem ele o `COPY . .`
levava o `.env` de desenvolvimento — com credencial de verdade — para dentro da
imagem.

---

## Validação

```bash
kubeconform -summary -strict -kubernetes-version 1.30.0 \
  base os-service billing-service execucao-service
```

Estado atual: **34 recursos em 21 arquivos, 0 inválidos.**

Vale rodar junto a conferência de filas e, desde 10/11, a de variáveis: um
ConfigMap que declara `EXCHANGE_EVENTOS` para um serviço que lê
`RABBITMQ_EXCHANGE` passa no `kubeconform` sem reclamar nada e o serviço cai no
default em silêncio.

---

## O que ainda não está aqui

| Falta | Observação |
|---|---|
| **Área do cliente no Kong** | `/api/public/ordens-servico`, com JWT RS256 (ADR-0004/0005 da Fase 3), continua declarada e **não implementada** no OS Service. Os prefixos de `ordens-servico` foram conferidos em 12/11; `clientes` e `veiculos` saíram. |
| **Migrations na subida** | Os bancos relacionais sobem vazios. A Execução já resolveu os índices do Mongo com `initContainer`; falta a mesma decisão para as migrations do Postgres do OS e do Billing. |

---

## Kong — o ponto único de entrada

`base/20-kong.yaml`, modo **DB-less**: a configuração inteira vive no ConfigMap,
versionada. Rota não se cria pelo Admin API — mesma regra das filas do RabbitMQ.

| Prefixo | Vai para | Origem |
|---|---|---|
| `/api/ordens-servico` | OS Service | `routes/api.php` ✓ 12/11 |
| `/api/public/ordens-servico` | OS Service, com **JWT RS256** | **não implementada** |
| `/api/orcamentos`, `/api/pagamentos` | Billing | `routes/api.php` |
| `/api/execucao` | Execução | `routes/api.php` |

`/api/ordens-servico` saiu do *a confirmar* em 12/11, quando a API do OS Service
foi escrita. Ela cobre as três rotas que existem: `POST` para abrir a OS,
`POST /{id}/diagnostico` para fechar o diagnóstico e iniciar a saga, e
`GET /{id}` para acompanhar.

**`/api/clientes` e `/api/veiculos` foram removidos.** Estavam ali porque a API
da Fase 3 os tinha. O OS Service não implementa nenhum dos dois, e não é
descuido: os domínios `Cliente` e `Veiculo` existem no repositório — 8 arquivos,
com `Cpf`, `Cnpj`, `Placa` e `DocumentoFiscal` — e não são referenciados por
**nada** fora de si mesmos. Zero controllers, zero repositórios, zero rotas,
zero testes, 0% de cobertura. É scaffolding da decomposição que ficou para trás.

Rota de gateway apontando para endpoint inexistente é pior que rota ausente: o
Kong encaminha e o cliente leva um 404 do serviço, como se o recurso existisse e
estivesse vazio.

`/api/public/ordens-servico` continua declarada porque a decisão é do grupo, mas
hoje ela encaminha para um endpoint que não existe.

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
