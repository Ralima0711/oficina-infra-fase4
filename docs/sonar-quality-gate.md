# SonarCloud e o quality gate — Fase 4

**Grupo 77 · as três métricas da Aula 4, traduzidas para o que o Sonar realmente aceita**

A Aula 4 destaca três métricas: **cobertura de testes**, **complexidade ciclomática** e
**débito técnico**. Duas entram no quality gate do Sonar. A terceira não — e não por
escolha nossa.

---

## O limite do plano, medido em 15/11

A organização está no **plano gratuito** do SonarQube Cloud. Ele analisa, mostra tudo e
aplica o quality gate embutido, mas recusa duas coisas, com esta mensagem:

> *You are exploring a paid feature. Your current plan does not allow you to assign
> custom Quality gates / Quality profiles to projects.*

Dá para **criar** um gate e um profile próprios. Não dá para **atribuir** nenhum dos dois
a um projeto. Na prática:

| O que a gente queria | Dá no plano gratuito? | O que ficou |
|---|---|---|
| Quality gate `Oficina Fase 4` | não | o `Sonar way` embutido, que já cobra as mesmas condições |
| Quality profile com `php:S1541` em `max = 10` | não | job `complexidade` no pipeline, com PHPMD |

Está escrito aqui em vez de omitido porque a versão anterior deste documento mandava
fazer as duas coisas, e as duas eram impossíveis. Documento que descreve um controle que
não executa é o mesmo erro do job de deploy da Fase 3.

---

## Por que complexidade ciclomática não entra num quality gate

Vale entender, independente de plano: no Sonar, complexidade ciclomática é uma **medida**
— um número por função, por arquivo, por projeto. O quality gate só aceita condições sobre
**ratings** (A a E) e percentuais. Não existe condição "complexidade ciclomática máxima"
para escolher.

Quem a enforçaria é uma **regra do quality profile** (`php:S1541`): função acima do limite
vira *issue*, issue de manutenibilidade derruba o **Maintainability Rating**, e aí o gate
pega. O caminho seria:

```
regra no quality profile  →  issue  →  Maintainability Rating  →  quality gate  →  merge bloqueado
```

Duas coisas quebram esse caminho aqui. A regra `php:S1541` vem **desativada** no
`Sonar way` de fábrica — conferido na tela da regra, que diz *"This rule isn't activated
on any quality profiles"*, com limite padrão 20. E ativá-la exige um profile próprio, que
o plano não deixa atribuir.

Por isso ela é cobrada no pipeline. Veja a Parte 3.

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

## Parte 2 — O quality gate é o `Sonar way`, e ele basta

Não há nada a criar. O gate embutido, que todo projeto novo recebe, tem exatamente estas
condições, todas em **New Code**:

| Métrica | Condição |
|---|---|
| **Coverage** | menor que **80%** → reprova |
| **Maintainability Rating** | pior que **A** → reprova (é o **débito técnico**) |
| Reliability Rating | pior que **A** → reprova |
| Security Rating | pior que **A** → reprova |
| Security Hotspots Reviewed | menor que **100%** → reprova |
| Duplicated Lines | maior que **3%** → reprova |

É a mesma tabela que a gente ia montar à mão. A única coisa que o gate próprio daria é o
nome, e o nome não reprova nada.

> **New Code, não Overall.** O gate avalia só o que o PR mudou. Em Overall, um
> repositório que começa em 40% reprova todo PR até alguém fazer um mutirão — e aí a
> equipe desliga o gate. Em New Code, código novo nasce coberto e a média sobe sozinha.

---

## Parte 3 — A complexidade mora no pipeline

O job `complexidade` do `ci-cd-servico.yml` roda **PHPMD** com a regra
`CyclomaticComplexity` em `reportLevel = 10` — o mesmo limite que `php:S1541` teria.

Duas decisões dentro dele:

**Só em pull request, e só nos arquivos do diff.** Medir o repositório inteiro hoje
reprovaria código que já estava lá antes da regra existir. Em 15/11 o OS Service tinha
zero funções acima de 10 em 255; o Billing tinha 7 e a Execução 1. Um gate que nasce
vermelho é desligado na primeira vez que incomoda — e aí não sobra gate nenhum. O limite
vale para o que o PR altera, e o resto sobe junto, arquivo por arquivo.

**Reprova de verdade.** O job falha, o check fica vermelho, o PR não entra. Não é
relatório.

Dez é o limite clássico de McCabe. Método que passa disso quase sempre tem mais de uma
responsabilidade — e o lugar mais provável de isso aparecer é o orquestrador da saga, que
é exatamente onde a gente **não** quer um método difícil de seguir.

Os limites são inputs do workflow, então um serviço pode apertar sem mexer nos outros:

```yaml
complexidade-maxima: 10   # padrão
pasta-fonte: app          # padrão
```

---

## Parte 4 — Fechar o circuito

Os checks existem mas não bloqueiam nada até virarem **required status check**:

Em cada um dos três repositórios → **Settings → Branches → main → Edit** →
*Require status checks to pass before merging* → marcar `SonarQube e quality gate` e
`Complexidade ciclomática`.

Cada um só aparece na lista **depois de rodar pelo menos uma vez**. Então: deixar um PR
rodar o pipeline inteiro primeiro, e aí voltar aqui.

---

## O que fica garantido no fim

| Métrica da Aula 4 | Como é garantida | Onde reprova |
|---|---|---|
| Cobertura de testes | duas vezes: o gate do pipeline lê o `clover.xml` e reprova abaixo do mínimo do serviço, e o `Sonar way` reprova de novo abaixo de 80% em New Code | job `testes` e job `sonar` |
| Débito técnico | Maintainability Rating A em New Code | job `sonar` |
| Complexidade ciclomática | PHPMD com limite 10 nos arquivos que o PR altera | job `complexidade` |

A cobertura é checada duas vezes de propósito. O gate local vale mesmo sem Sonar
configurado, e falha no job do próprio serviço em vez de vir de um serviço externo
minutos depois.

---

*Grupo 77 · FIAP SOAT Pós-Tech · Fase 4*
