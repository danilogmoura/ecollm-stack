#!/usr/bin/env python3
"""Fase A do S102 — inventário travado dos modelos NovAI no proxy.

Determinístico, offline (não chama rede nem gasta saldo): lê
`litellm/config.yaml`, extrai cada grupo `novai-*` com seu upstream
(`litellm_params.model`) e classifica por modalidade usando os PREFIXOS DE
FAMÍLIA canônicos (S100). Vídeo/3D NÃO são grupos roteáveis — vivem só como
endpoints de passthrough; este script os registra separadamente.

Saída: CSV em reports/novai-test-matrix.csv (reports/ é gitignored = observação).
Uso: .venv/bin/python eval/novai_inventory.py [--config litellm/config.yaml]
     [--out reports/novai-test-matrix.csv]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Prefixos de família canônicos (S100). Ordem importa: testa o mais específico
# primeiro. Chat = qualquer novai-* que não case com um prefixo não-chat.
NONCHAT_PREFIXES = {
    "novai-embed-": "embedding",
    "novai-image-": "image",
    "novai-tts-": "tts",
    "novai-asr-": "asr",
}

MODEL_NAME_RE = re.compile(r"^\s*-\s*model_name:\s*(\S+)\s*$")
UPSTREAM_RE = re.compile(r"^\s*model:\s*(\S+)\s*$")


def classify(name: str) -> str:
    for prefix, modality in NONCHAT_PREFIXES.items():
        if name.startswith(prefix):
            return modality
    # chat: thinking OFF tem sufixo -fast; ON é a base.
    return "chat-fast" if name.endswith("-fast") else "chat"


def parse_config(text: str) -> list[dict]:
    """Percorre o bloco model_list: casa model_name -> próximo upstream."""
    rows: list[dict] = []
    pending: str | None = None
    in_model_list = False
    for line in text.splitlines():
        if re.match(r"^model_list:\s*$", line):
            in_model_list = True
            continue
        # fim do model_list: próxima chave de topo (sem recuo, termina em ':')
        if in_model_list and re.match(r"^[a-z_]+:", line):
            break
        m = MODEL_NAME_RE.match(line)
        if m:
            name = m.group(1)
            if name.startswith("novai-"):
                pending = name
            else:
                pending = None
            continue
        u = UPSTREAM_RE.match(line)
        if u and pending is not None:
            upstream = u.group(1)
            if upstream.startswith("openai/"):
                upstream = upstream[len("openai/"):]
            rows.append(
                {
                    "group": pending,
                    "modality": classify(pending),
                    "upstream_id": upstream,
                }
            )
            pending = None
    return rows


PASSTHROUGH = [
    {
        "group": "(passthrough) /novai/video",
        "modality": "video-passthrough",
        "upstream_id": "https://aiapi-pro.com/v1/video/generations",
    },
    {
        "group": "(passthrough) /novai/3d",
        "modality": "3d-passthrough",
        "upstream_id": "https://aiapi-pro.com/v1/three_d/generations",
    },
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="litellm/config.yaml")
    ap.add_argument("--out", default="reports/novai-test-matrix.csv")
    args = ap.parse_args(argv)

    cfg = Path(args.config)
    if not cfg.exists():
        print(f"ERRO: config não encontrado: {cfg}", file=sys.stderr)
        return 2
    rows = parse_config(cfg.read_text(encoding="utf-8"))
    all_rows = rows + PASSTHROUGH

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "modality", "upstream_id", "status", "evidence"])
        for r in all_rows:
            w.writerow([r["group"], r["modality"], r["upstream_id"], "untested", ""])

    # resumo por modalidade
    counts: dict[str, int] = {}
    for r in all_rows:
        counts[r["modality"]] = counts.get(r["modality"], 0) + 1
    print(f"Inventário gravado em {out}")
    print(f"Total grupos roteáveis: {len(rows)}  (+{len(PASSTHROUGH)} passthrough)")
    for modality in sorted(counts):
        print(f"  {modality:18s} {counts[modality]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
