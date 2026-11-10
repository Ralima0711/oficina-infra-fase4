#!/usr/bin/env bash
#
# cadastra-secrets-sonar.sh — Tech Challenge SOAT Fase 4 (Grupo 77)
#
# Cadastra o SONAR_TOKEN nos quatro repositorios de uma vez.
#
# Diferente do atualiza-secrets-fase4.sh, este nao se repete: o token do Sonar
# nao expira a cada reset do lab. Roda uma vez, e so de novo se o token for
# revogado ou rotacionado.
#
# A chave do projeto e a organizacao NAO entram aqui: nao sao segredo e vivem
# versionadas no sonar-project.properties de cada servico, onde dao para
# conferir num diff.
#
# Pre-requisito: gh auth login
#
# Uso:
#   bash cadastra-secrets-sonar.sh

set -euo pipefail

OWNER="Ralima0711"

REPOS=(
  oficina-os-service
  oficina-billing-service
  oficina-execucao-service
  oficina-infra-fase4
)

if ! gh auth status >/dev/null 2>&1; then
  echo "ERRO: o gh nao esta autenticado. Rode: gh auth login"
  exit 1
fi

echo "O SONAR_TOKEN aparece uma unica vez no SonarCloud, na tela de"
echo "'Analyze new project' -> GitHub Actions. Se voce perdeu, gere outro em"
echo "My Account -> Security."
echo

# -s nao ecoa a digitacao; o valor nao entra no historico do shell nem na tela.
read -r -s -p "Cole o SONAR_TOKEN: " SONAR_TOKEN
echo
echo

if [ -z "${SONAR_TOKEN}" ]; then
  echo "ERRO: token vazio, nada foi cadastrado."
  exit 1
fi

# Um token do SonarCloud comeca com 'sq' ou e um hex de 40 caracteres.
# Nao e validacao de verdade, e so para pegar um Ctrl+V que veio errado.
if ! printf '%s' "${SONAR_TOKEN}" | grep -qE '^(sq[a-z]_[A-Za-z0-9]{20,}|[0-9a-f]{40})$'; then
  echo "AVISO: isso nao parece um token do SonarCloud."
  read -r -p "Cadastrar assim mesmo? [s/N] " resposta
  case "${resposta}" in
    s|S|sim|SIM) ;;
    *) echo "Cancelado, nada foi cadastrado."; exit 1 ;;
  esac
  echo
fi

echo "Cadastrando em ${#REPOS[@]} repositorios..."
echo

for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  if gh secret set SONAR_TOKEN --repo "${OWNER}/${repo}" --body "${SONAR_TOKEN}" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "FALHOU (sem permissao de admin neste repo?)"
  fi
done

unset SONAR_TOKEN

echo
echo "Conferindo:"
for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  gh secret list --repo "${OWNER}/${repo}" --json name --jq '[.[].name] | join(", ")' 2>/dev/null \
    || gh secret list --repo "${OWNER}/${repo}" | awk '{printf "%s ", $1}'
  echo
done

echo
echo "Falta, e e manual (ver sonar-quality-gate.md):"
echo "  1. criar o quality gate 'Oficina Fase 4' e aplicar aos 3 projetos"
echo "  2. copiar o perfil PHP e ativar a regra php:S1541 com max = 10"
echo "  3. desligar o Automatic Analysis nos 3 projetos"
echo "  4. marcar o check do Sonar como required na protecao da main"
