#!/usr/bin/env python3
"""Confere as variaveis que os manifestos entregam contra as que o codigo le.

O erro que este script pega nao aparece em teste, nao aparece em build e nao
aparece no `docker compose up`: aparece no cluster, no dia do deploy.

Em 12/11 ele teria pegado tres de uma vez, todos encontrados a mao:

  JWT_PUBLIC_KEY        injetada nos tres workloads do OS Service, lida por
                        NINGUEM. O pod passava a exigir o Secret os-jwt para
                        subir e morria com CreateContainerConfigError por uma
                        variavel que ninguem consome.

  MONGO_USERNAME        injetadas no Deployment e no worker da Execucao, lidas
  MONGO_PASSWORD        por ninguem: config/mongodb.php le MONGO_URI e so ela.
                        A conexao ia sem credencial contra um Mongo com
                        autenticacao, e a primeira escrita falhava.

  FILA_*, MONGO_*       no ConfigMap do OS Service, sem nenhum leitor.

A direcao que importa e essa: variavel ENTREGUE e NAO LIDA. O contrario
(variavel lida e nao entregue) e barulho no Laravel, onde quase todo env() tem
default — e por isso MONGO_URI, que TEM default, passou despercebida: o
problema nao era a ausencia dela, era a presenca das outras duas.

O que este script NAO pega: argumento de comando. As filas que cada worker
consome vem do `command:` do Deployment, nao de env — e foi assim que
billing.anular-orcamento e billing.estornar-pagamento ficaram sem consumidor no
cluster ate 12/11. Para isso serve o confere-filas.py, e nem ele cobre o
`--fila` do command. Fica anotado.

uso:
    python3 k8s/scripts/confere-env.py
    python3 k8s/scripts/confere-env.py --servicos /caminho/para/os-pais
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import yaml

AQUI = pathlib.Path(__file__).resolve().parent
K8S = AQUI.parent
RAIZ = K8S.parent

# pasta de manifestos -> nome do repositorio do servico
SERVICOS = {
    "os-service": "oficina-os-service",
    "billing-service": "oficina-billing-service",
    "execucao-service": "oficina-execucao-service",
}

# Variaveis que o Laravel ou a plataforma consomem sem aparecer em config/.
# Cada uma precisa de motivo escrito: lista de excecao sem motivo vira lixo.
TOLERADAS = {
    "APP_ENV": "lida pelo framework antes de qualquer config/",
    "APP_DEBUG": "idem",
    "APP_KEY": "lida pelo Encrypter via config/app.php do proprio Laravel",
    "LOG_CHANNEL": "lida por config/logging.php do Laravel",
    "LOG_LEVEL": "idem",
    "NEW_RELIC_LICENSE_KEY": "nenhum PHP le direto: o workload a usa para montar OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "lida pelo SDK do OpenTelemetry",
    "OTEL_SERVICE_NAME": "idem",
    "OTEL_EXPORTER_OTLP_HEADERS": "idem; leva a license key, montada no workload a partir de NEW_RELIC_LICENSE_KEY",
}


def lidas_pelo_codigo(repo: pathlib.Path) -> set[str]:
    """Nomes que aparecem em env('NOME') em qualquer arquivo de config/."""
    nomes: set[str] = set()
    config = repo / "config"

    if not config.is_dir():
        return nomes

    for arquivo in config.glob("*.php"):
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        nomes.update(re.findall(r"env\(\s*['\"]([A-Z0-9_]+)['\"]", texto))

    return nomes


def entregues_pelos_manifestos(pasta: pathlib.Path) -> dict[str, str]:
    """Nome -> arquivo que entrega, somando ConfigMap e env dos workloads.

    So os arquivos de CONFIGURACAO e APLICACAO, pela convencao de numeracao do
    repositorio: 20 bancos, 30 configuracao, 40 aplicacao. Os StatefulSets de
    Postgres, Mongo e Redis entregam POSTGRES_USER, MONGO_INITDB_ROOT_USERNAME
    e afins, que sao lidos pela IMAGEM do banco, nao pelo PHP — compara-los
    com o config/ do servico nao quer dizer nada.
    """
    entregues: dict[str, str] = {}

    for arquivo in sorted(pasta.glob("[34]*.yaml")):
        for doc in yaml.safe_load_all(arquivo.read_text(encoding="utf-8")):
            if not doc:
                continue

            onde = arquivo.name

            if doc.get("kind") == "ConfigMap":
                for nome in (doc.get("data") or {}):
                    entregues.setdefault(nome, onde)
                continue

            if doc.get("kind") not in {"Deployment", "StatefulSet"}:
                continue

            spec = doc["spec"]["template"]["spec"]
            for grupo in ("initContainers", "containers"):
                for c in spec.get(grupo) or []:
                    for e in c.get("env") or []:
                        entregues.setdefault(e["name"], onde)

    return entregues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--servicos",
        default=str(RAIZ.parent),
        help="pasta que contem os repositorios dos servicos (padrao: a irma desta)",
    )
    args = p.parse_args()
    pais = pathlib.Path(args.servicos).resolve()

    problemas: list[str] = []
    conferidos = 0

    for pasta, repo_nome in SERVICOS.items():
        manifestos = K8S / pasta
        repo = pais / repo_nome

        if not manifestos.is_dir():
            problemas.append(f"pasta de manifestos nao encontrada: {manifestos}")
            continue

        if not (repo / "config").is_dir():
            print(f"  {pasta}: repositorio nao encontrado em {repo}, pulando")
            continue

        conferidos += 1
        lidas = lidas_pelo_codigo(repo)
        entregues = entregues_pelos_manifestos(manifestos)

        mortas = {
            nome: onde
            for nome, onde in entregues.items()
            if nome not in lidas and nome not in TOLERADAS
        }

        print(f"  {pasta}: {len(entregues)} entregues, {len(lidas)} lidas em config/")

        for nome, onde in sorted(mortas.items()):
            problemas.append(
                f"{pasta}/{onde} entrega {nome}, e nenhum env() em "
                f"{repo_nome}/config/ le essa variavel"
            )

    if conferidos == 0:
        print(
            "ERRO: nenhum repositorio de servico encontrado. Use --servicos "
            "apontando para a pasta que contem os quatro repositorios.",
            file=sys.stderr,
        )
        return 1

    if problemas:
        print()
        for item in problemas:
            print(f"  DIVERGENCIA: {item}")
        print()
        print(
            "Variavel entregue e nao lida nao e inofensiva: quando vem de "
            "Secret, o pod passa a EXIGIR esse Secret para subir e morre com "
            "CreateContainerConfigError por algo que ninguem consome."
        )
        return 1

    print("ok: toda variavel entregue tem quem a leia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
