#!/usr/bin/env python3
"""Gera base/11-rabbitmq-definitions.yaml a partir de rabbitmq/definitions.json.

A topologia do RabbitMQ vive em UM lugar so: rabbitmq/definitions.json.
O compose local monta o arquivo direto; o cluster precisa dele dentro de um
ConfigMap. Este script faz a traducao, para ninguem manter as duas copias a mao.

uso:
    python3 scripts/gera-configmap-definitions.py > base/11-rabbitmq-definitions.yaml
"""
import json
import pathlib
import sys
import textwrap

AQUI = pathlib.Path(__file__).resolve().parent
K8S = AQUI.parent

CABECALHO = """# ConfigMap gerado a partir de rabbitmq/definitions.json do oficina-infra-fase4.
# NAO editar aqui: editar o definitions.json e regerar, senao o compose local
# e o cluster divergem — e divergencia de topologia so aparece na demonstracao.
#
# regerar:  python3 scripts/gera-configmap-definitions.py > base/11-rabbitmq-definitions.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: rabbitmq-definitions
  namespace: oficina
  labels:
    app.kubernetes.io/name: rabbitmq
    app.kubernetes.io/part-of: oficina-fase4
data:
  definitions.json: |
"""


def acha_raiz_do_repo(inicio: pathlib.Path) -> pathlib.Path | None:
    """Sobe a arvore procurando quem tem rabbitmq/definitions.json.

    Os manifestos vivem em k8s/ dentro do oficina-infra-fase4, e o
    definitions.json fica na raiz do repo. Procurar em vez de fixar o caminho
    deixa o script rodar da raiz ou de dentro de k8s/, sem pegadinha.
    """
    for diretorio in [inicio, *inicio.parents]:
        if (diretorio / "rabbitmq" / "definitions.json").is_file():
            return diretorio
    return None


def main() -> int:
    raiz = acha_raiz_do_repo(AQUI)
    if raiz is None:
        print("ERRO: nao achei rabbitmq/definitions.json subindo a partir de "
              f"{AQUI}", file=sys.stderr)
        return 1
    topologia = json.loads((raiz / "rabbitmq" / "definitions.json").read_text(encoding="utf-8"))
    corpo = textwrap.indent(json.dumps(topologia, indent=2, ensure_ascii=False), " " * 4)
    sys.stdout.write(CABECALHO + corpo + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
