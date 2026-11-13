#!/usr/bin/env bash
#
# cadastra-secrets-dockerhub.sh — Tech Challenge SOAT Fase 4 (Grupo 77)
#
# Cadastra DOCKERHUB_USERNAME e DOCKERHUB_TOKEN nos tres servicos.
#
# Por que existe: em 13/11 a CI do OS Service rodou pela primeira vez e o job
# de testes passou — mas o run ficou vermelho em "Build e push da imagem", com
# "Username and password required". Os dois secrets nunca tinham sido
# cadastrados, porque ate entao nenhum pipeline tinha chegado nesse job.
#
# Como o do Sonar, este nao se repete: token do Docker Hub nao expira a cada
# reset do lab. Roda uma vez, e so de novo se for revogado.
#
# O infra fica de fora: ele nao tem imagem.
#
# Pre-requisito: gh auth login
#
# Uso:
#   bash cadastra-secrets-dockerhub.sh

set -euo pipefail

OWNER="Ralima0711"

REPOS=(
  oficina-os-service
  oficina-billing-service
  oficina-execucao-service
)

if ! gh auth status >/dev/null 2>&1; then
  echo "ERRO: o gh nao esta autenticado. Rode: gh auth login"
  exit 1
fi

echo "O token do Docker Hub se gera em hub.docker.com ->"
echo "Account Settings -> Personal access tokens -> Generate new token."
echo "Permissao: Read & Write (o pipeline faz push da imagem)."
echo
echo "O usuario e o do Docker Hub, que nas tags dos manifestos e 'ralima0711'."
echo

read -r -p "Usuario do Docker Hub: " DOCKERHUB_USERNAME

if [ -z "${DOCKERHUB_USERNAME}" ]; then
  echo "ERRO: usuario vazio, nada foi cadastrado."
  exit 1
fi

# -s nao ecoa: o token nao entra no historico do shell nem fica na tela.
read -r -s -p "Cole o token do Docker Hub: " DOCKERHUB_TOKEN
echo
echo

if [ -z "${DOCKERHUB_TOKEN}" ]; then
  echo "ERRO: token vazio, nada foi cadastrado."
  exit 1
fi

echo "Cadastrando em ${#REPOS[@]} repositorios..."
echo

for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  if gh secret set DOCKERHUB_USERNAME --repo "${OWNER}/${repo}" --body "${DOCKERHUB_USERNAME}" >/dev/null 2>&1 \
     && gh secret set DOCKERHUB_TOKEN --repo "${OWNER}/${repo}" --body "${DOCKERHUB_TOKEN}" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "FALHOU (sem permissao de admin neste repo?)"
  fi
done

unset DOCKERHUB_TOKEN

echo
echo "Conferindo:"
for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  gh secret list --repo "${OWNER}/${repo}" --json name --jq '[.[].name] | join(", ")' 2>/dev/null \
    || gh secret list --repo "${OWNER}/${repo}" | awk '{printf "%s ", $1}'
  echo
done

echo
echo "Depois disso o job 'Build e push da imagem' passa a publicar"
echo "ralima0711/<servico>:<sha-curto> e :latest a cada merge na main."
