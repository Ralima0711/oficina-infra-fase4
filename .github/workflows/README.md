# Pipeline dos serviços — Fase 4

**Grupo 77 · um workflow reutilizável, três chamadores**

O enunciado pede *"deploy automatizado de ao menos 1 microsserviço com validação
de testes"* e **80% de cobertura por serviço com quality gate**. Hoje nada disso
é obrigado por máquina nenhuma: o billing tem CI com `coverage: none`, a execução
não tem pipeline, e os 80% existem só como combinado.

Isto resolve as duas coisas no mesmo lugar.

---

## Como está organizado

```
oficina-infra-fase4/
└── .github/workflows/
    └── ci-cd-servico.yml      ← o pipeline de verdade

oficina-os-service/
oficina-billing-service/
oficina-execucao-service/
└── .github/workflows/
    └── ci.yml                 ← 20 linhas, só os parâmetros do serviço
```

Mudança de pipeline se faz **uma vez**, no infra, para os três. É a mesma regra
da topologia do RabbitMQ: uma fonte, vários consumidores.

---

## Os quatro jobs

| Job | Quando roda | O que reprova |
|---|---|---|
| **testes** | sempre | cobertura abaixo de 80% |
| **sonar** | se houver chave do projeto | quality gate reprovado |
| **imagem** | só na `main` | falha de build |
| **deploy** | só no **disparo manual** | credencial faltando, cluster mudo, rollout travado |

### O gate de cobertura é local, não do Sonar

O job de testes lê o `clover.xml` e falha sozinho abaixo do mínimo. De propósito:
assim os 80% valem mesmo antes de o Sonar estar configurado, e a reprovação
aparece no job do serviço em vez de vir de um serviço externo minutos depois.

O Sonar continua valendo — é ele que mede as outras duas métricas que a Aula 4
destaca, **complexidade ciclomática** e **débito técnico**, que se configuram no
quality gate dentro do próprio Sonar.

### Bancos de verdade no job de testes

Postgres, Mongo, Redis e RabbitMQ sobem como *service containers* em todos os
repositórios, mesmo que cada serviço use só uma parte. Não dá para declarar
`services` condicionalmente a partir de um input, e a alternativa seria um
pipeline por serviço — que é o que este arquivo existe para evitar. Custa cerca
de 30 segundos por job.

Em troca, o **nível 2 da pirâmide** (integração) roda contra banco de verdade, e
não contra mock. É onde aparece o que o mock esconde: mapeamento objeto-banco,
constraint, lock otimista, mensagem que não chega.

---

## Por que o deploy é manual

**Esta é a decisão que mais vale explicar.**

O job de deploy **falha** quando falta `KUBECONFIG` ou credencial da AWS. Não pula,
não avisa, não passa: falha em vermelho.

Isso é resposta direta à Fase 3, onde o job de deploy existia nos quatro
repositórios, rodava em 4 a 6 segundos, caía num ramo chamado *"Inform Minikube
Local Deployment"* e ninguém percebeu a fase inteira que nada nunca foi aplicado.
Um pipeline que "passa" sem fazer nada é pior que um que não existe.

Mas as credenciais do AWS Academy expiram em horas. Se o deploy rodasse a cada
push, a `main` ficaria vermelha quase sempre e todo mundo aprenderia a ignorar o
vermelho — a mesma doença, pelo avesso.

Por isso: **push e PR rodam testes, cobertura, Sonar e imagem. O deploy só no
disparo manual.** Que é também o que o cronograma já tinha decidido —
`docker-compose` para o dia a dia, EKS para a evidência e a gravação.

Para gerar a evidência:

1. `bash atualiza-secrets-fase4.sh` **dentro da janela do lab**
2. Actions → CI/CD → Run workflow

---

## Secrets

| Secret | Onde | Muda a cada reset do lab |
|---|---|---|
| `AWS_ACCESS_KEY_ID` · `AWS_SECRET_ACCESS_KEY` · `AWS_SESSION_TOKEN` | os 4 repos | **sim** |
| `KUBECONFIG` (base64) | os 4 repos | **sim** |
| `SONAR_TOKEN` · `SONAR_ORGANIZATION` | os 4 repos | não |
| `DOCKERHUB_USERNAME` · `DOCKERHUB_TOKEN` | os 3 serviços | não |

Os quatro primeiros são o que o `atualiza-secrets-fase4.sh` atualiza de uma vez.

O chamador usa `secrets: inherit`, então o workflow reutilizável enxerga os
secrets do repositório que o chamou — nenhum valor passa por arquivo.

---

## Instalação

**No `oficina-infra-fase4`:** `.github/workflows/ci-cd-servico.yml`

**Em cada serviço:** `.github/workflows/ci.yml`, a partir do chamador
correspondente em `chamadores/`. No billing, ele **substitui** o `ci.yml` atual
(que tem `coverage: none`).

Depois do primeiro verde, ligar o job como *required status check* na proteção
da `main` dos três repositórios. Sem isso o gate existe mas não bloqueia nada.

---

## O que ainda falta

| Falta | Quem |
|---|---|
| Criar os projetos no Sonar e cadastrar `SONAR_TOKEN` / `SONAR_ORGANIZATION` | Gustavo |
| Configurar o quality gate nas três métricas | Gustavo |
| Ligar o `confere-filas.py` no CI dos serviços que têm cópia local da topologia | David |
| Marcar o job como required check na proteção da `main` | Roberta |

---

*Grupo 77 · FIAP SOAT Pós-Tech · Fase 4*
