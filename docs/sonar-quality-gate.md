# SonarCloud e o quality gate — Fase 4

**Grupo 77 · as três métricas da Aula 4, traduzidas para o que o Sonar realmente aceita**

A Aula 4 destaca três métricas: **cobertura de testes**, **complexidade ciclomática** e
**débito técnico**. Duas delas entram direto no quality gate. A terceira não — e é a
primeira coisa que vale entender, porque uma configuração ingênua diz que cobre as três
quando na verdade cobre duas.

---

## Por que complexidade ciclomática não entra no gate

No Sonar, complexidade ciclomática é uma **medida** — um número por função, por arquivo,
por projeto. O quality gate só aceita condições sobre **ratings** (A a E) e percentuais.
Não existe condição "complexidade ciclomática máxima" para escolher.

Quem enforça complexidade é uma **regra do quality profile**: se uma função passa do
limite, vira *issue*. Aí sim o gate pega, pela condição de **Maintainability Rating**,
porque issue de manutenibilidade empurra o rating para baixo.

Então o caminho é:

```
regra no quality profile  →  issue  →  Maintainability Rating  →  quality gate  →  merge bloqueado
```

Vale saber disso na defesa: a pergunta "como vocês garantem complexidade?" tem uma
resposta boa, que é essa, e uma ruim, que é apontar para um gráfico.

---

## Parte 1 — Criar os projetos

**Isso é da Roberta: envolve conta, autorização OAuth no GitHub e token.**

1. Entrar em **sonarcloud.io** com a conta do GitHub (`Ralima0711`)
2. **+** → *Analyze new project* → autorizar a organização
3. Importar os três repositórios:
   - `oficina-os-service`
   - `oficina-billing-service`
   - `oficina-execucao-service`
4. Em cada um, escolher **GitHub Actions** como método de análise.
   O SonarCloud mostra o `SONAR_TOKEN` — **é a única vez que ele aparece.**
5. Em *Administration → Analysis Method*, **desligar** o Automatic Analysis.
   Se ficar ligado, ele briga com o scanner do pipeline e a análise do CI é recusada.

A chave do projeto e a organização já estão no `sonar-project.properties` de cada
serviço — confira se batem com o que o SonarCloud gerou. Se divergirem, o certo é
mudar o arquivo, não o projeto.

### O secret

Um só, nos quatro repositórios:

```bash
bash cadastra-secrets-sonar.sh
```

O script pede o token uma vez, com a digitação oculta, e cadastra nos quatro. Nenhum
valor passa por arquivo nem por histórico de shell.

---

## Parte 2 — O quality gate

Em **Quality Gates → Create**, nome `Oficina Fase 4`, condições em **New Code**:

| Métrica | Condição | Por quê |
|---|---|---|
| **Coverage** | menor que **80%** → reprova | É o número do enunciado |
| **Maintainability Rating** | pior que **A** → reprova | É o **débito técnico**, e é por aqui que a complexidade chega |
| Reliability Rating | pior que **A** → reprova | Bug novo não entra |
| Security Rating | pior que **A** → reprova | |
| Security Hotspots Reviewed | menor que **100%** → reprova | Barato: obriga alguém a olhar, não a corrigir |
| Duplicated Lines | maior que **3%** → reprova | Copiar e colar entre serviços é o risco real aqui |

Depois: **Projects** → adicionar os três.

> **New Code, não Overall.** O gate avalia só o que o PR mudou. Em Overall, um
> repositório que começa em 40% reprova todo PR até alguém fazer um mutirão — e aí a
> equipe desliga o gate. Em New Code, código novo nasce coberto e a média sobe sozinha.

---

## Parte 3 — A regra de complexidade

Sem isto, o gate acima cobre cobertura e débito técnico, mas **não** complexidade.

1. **Quality Profiles** → PHP → o perfil *Sonar way* → **Copy**, com o nome
   `Oficina Fase 4 — PHP`
2. Procurar a regra **"Cyclomatic Complexity of functions should not be too high"**
   (chave `php:S1541`)
3. Ativar, com o parâmetro **`max = 10`**
4. **Projects** → aplicar o perfil aos três serviços

Dez é o limite clássico de McCabe e é o que a maioria dos times usa. Método que passa
disso quase sempre tem mais de uma responsabilidade — e, no nosso caso, o lugar mais
provável de isso aparecer é o orquestrador da saga, que é exatamente onde a gente **não**
quer um método difícil de seguir.

> Se a chave da regra não bater, procure por *"Cyclomatic Complexity"* na busca de regras
> do perfil PHP. O nome é estável, a chave pode variar entre versões.

---

## Parte 4 — Fechar o circuito

O gate existe mas não bloqueia nada até virar **required status check**:

Em cada um dos três repositórios → **Settings → Branches → main → Edit** →
*Require status checks to pass before merging* → marcar o check do Sonar.

Ele só aparece na lista **depois que rodar pelo menos uma vez**. Então: mergear um PR
qualquer primeiro, deixar o pipeline rodar, e aí voltar aqui.

---

## O que fica garantido no fim

| Métrica da Aula 4 | Como é garantida | Onde reprova |
|---|---|---|
| Cobertura de testes | duas vezes: o gate local do pipeline lê o `clover.xml` e reprova abaixo de 80%, e o Sonar reprova de novo | job `testes` e job `sonar` |
| Débito técnico | Maintainability Rating A em New Code | job `sonar` |
| Complexidade ciclomática | regra `php:S1541` com `max = 10` → issue → Maintainability Rating | job `sonar` |

A cobertura é checada duas vezes de propósito. O gate local vale mesmo sem Sonar
configurado, e falha no job do próprio serviço em vez de vir de um serviço externo
minutos depois.

---

*Grupo 77 · FIAP SOAT Pós-Tech · Fase 4*
