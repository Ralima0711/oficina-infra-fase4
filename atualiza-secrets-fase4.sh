#!/usr/bin/env bash
#
# atualiza-secrets-fase4.sh — Tech Challenge SOAT Fase 4 (Grupo 77)
#
# O AWS Academy reseta o laboratorio e troca as credenciais a cada sessao.
# Este script atualiza, nos QUATRO repositorios de uma vez:
#
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
#   KUBECONFIG   <- a novidade da Fase 4
#
# Por que o KUBECONFIG entra aqui, e nao "uma vez so":
# o kubeconfig do EKS nao guarda credencial — ele chama `aws eks get-token`
# na hora. Entao ele so funciona enquanto as tres chaves acima forem validas,
# e o cluster muda de endpoint a cada recriacao do lab. Na Fase 3 o secret
# nunca foi cadastrado e o job de deploy passou a fase inteira caindo no ramo
# "Inform Minikube Local Deployment", em 4 a 6 segundos, sem ninguem notar.
#
# Pre-requisitos (uma vez so):
#   1. GitHub CLI   -> https://cli.github.com   e depois `gh auth login`
#   2. AWS CLI      -> `aws --version`
#   3. kubectl
#
# Uso, depois de cada reset do lab:
#   1. No AWS Academy: "AWS Details" -> "AWS CLI", copie o bloco para
#      ~/.aws/credentials (o mesmo bloco [default] de sempre).
#   2. bash atualiza-secrets-fase4.sh
#
# Ou exportando as variaveis, sem mexer em arquivo:
#   AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=... \
#     bash atualiza-secrets-fase4.sh

set -euo pipefail

OWNER="Ralima0711"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
CLUSTER="${EKS_CLUSTER:-}"        # vazio = descobre sozinho

REPOS=(
  oficina-os-service
  oficina-billing-service
  oficina-execucao-service
  oficina-infra-fase4
)

CRED="${HOME}/.aws/credentials"

ler_credencial() {
  [ -f "$CRED" ] || return 0
  grep -E "^[[:space:]]*$1[[:space:]]*=" "$CRED" | head -1 | sed -E "s/^[^=]+=[[:space:]]*//" | tr -d '\r'
}

b64() {
  # -w0 no GNU, sem quebra de linha no BSD/macOS
  base64 -w0 2>/dev/null || base64 | tr -d '\n'
}

AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-$(ler_credencial aws_access_key_id)}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-$(ler_credencial aws_secret_access_key)}"
AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN:-$(ler_credencial aws_session_token)}"

if [ -z "${AWS_ACCESS_KEY_ID}" ] || [ -z "${AWS_SECRET_ACCESS_KEY}" ]; then
  echo "ERRO: nao achei as credenciais."
  echo "Cole o bloco do 'AWS Details' em ${CRED} ou exporte as variaveis antes de rodar."
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "ERRO: o gh nao esta autenticado. Rode: gh auth login"
  exit 1
fi

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_DEFAULT_REGION="${REGION}"

# ---------------------------------------------------------------- KUBECONFIG
echo "Procurando o cluster EKS na regiao ${REGION}..."

if [ -z "${CLUSTER}" ]; then
  CLUSTER="$(aws eks list-clusters --query 'clusters[0]' --output text 2>/dev/null || true)"
fi

KUBECONFIG_B64=""

if [ -z "${CLUSTER}" ] || [ "${CLUSTER}" = "None" ]; then
  echo "  AVISO: nenhum cluster EKS encontrado."
  echo "  O lab provavelmente ainda nao subiu o cluster, ou as credenciais expiraram."
  echo "  As chaves da AWS serao atualizadas mesmo assim; o KUBECONFIG fica para depois."
else
  echo "  cluster: ${CLUSTER}"
  TMP_KUBECONFIG="$(mktemp)"
  trap 'rm -f "${TMP_KUBECONFIG}"' EXIT

  KUBECONFIG="${TMP_KUBECONFIG}" \
    aws eks update-kubeconfig --name "${CLUSTER}" --region "${REGION}" >/dev/null

  # prova de vida: se o kubectl nao falar com o cluster, nao adianta cadastrar
  if KUBECONFIG="${TMP_KUBECONFIG}" kubectl get nodes >/dev/null 2>&1; then
    KUBECONFIG_B64="$(b64 < "${TMP_KUBECONFIG}")"
    echo "  kubectl respondeu: o kubeconfig e valido"
  else
    echo "  AVISO: o kubectl nao conseguiu falar com o cluster."
    echo "  Nao vou cadastrar um KUBECONFIG que ja nasce quebrado."
  fi
fi

# ------------------------------------------------------------------- secrets
echo
echo "Atualizando secrets em ${#REPOS[@]} repositorios..."
echo

for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  gh secret set AWS_ACCESS_KEY_ID     --repo "${OWNER}/${repo}" --body "${AWS_ACCESS_KEY_ID}"     >/dev/null
  gh secret set AWS_SECRET_ACCESS_KEY --repo "${OWNER}/${repo}" --body "${AWS_SECRET_ACCESS_KEY}" >/dev/null
  gh secret set AWS_SESSION_TOKEN     --repo "${OWNER}/${repo}" --body "${AWS_SESSION_TOKEN}"     >/dev/null
  if [ -n "${KUBECONFIG_B64}" ]; then
    gh secret set KUBECONFIG          --repo "${OWNER}/${repo}" --body "${KUBECONFIG_B64}"        >/dev/null
    echo "ok (com KUBECONFIG)"
  else
    echo "ok (sem KUBECONFIG)"
  fi
done

echo
echo "Conferindo o que ficou cadastrado:"
for repo in "${REPOS[@]}"; do
  printf '  %-28s ' "$repo"
  gh secret list --repo "${OWNER}/${repo}" --json name --jq '[.[].name] | join(", ")' 2>/dev/null \
    || gh secret list --repo "${OWNER}/${repo}" | awk '{printf "%s ", $1}'
  echo
done

echo
echo "Secrets que NAO mudam a cada reset — cadastrar uma vez, por repositorio:"
echo "  todos                      : SONAR_TOKEN NEW_RELIC_LICENSE_KEY"
echo "  os / billing / execucao    : DOCKERHUB_USERNAME DOCKERHUB_TOKEN"
echo "  os / billing / execucao    : DB_USERNAME DB_PASSWORD DB_DATABASE"
echo "  oficina-billing-service    : MERCADOPAGO_ACCESS_TOKEN (sandbox)"
echo
echo "Lembrete: rode este script DENTRO da janela do lab, logo antes do deploy"
echo "que voce quer que fique registrado no Actions. As credenciais do Academy"
echo "expiram em horas — secret atualizado ontem nao serve para o pipeline de hoje."
