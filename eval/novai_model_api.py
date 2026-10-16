"""Extrai o MÁXIMO de informação de cada modelo NovAI via API e salva.

Combina duas fontes:
  1. ``GET /v1/models`` (metadados: id, owned_by, pricing, type) — via proxy.
  2. Sondas de capacidade por modelo (chat, thinking, tools, stream, embeddings,
     image, tts, asr) — reaproveita ``make_sender``/``verdict_*`` de
     ``eval.novai_test``.

Saída: ``reports/novai-model-api.json`` (um registro por modelo).

Padrão do repo: parse PURO + transporte INJETÁVEL (sender) para testes offline.
Rede só com ``--live``.

Uso:
    python -m eval.novai_model_api --live
    python -m eval.novai_model_api --live --family chat --sleep 1.1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import novai_test as N

OUT_DEFAULT = "reports/novai-model-api.json"


@dataclass
class ModelInfo:
    """Tudo que conseguimos saber de um modelo via API."""

    id: str
    owned_by: str | None = None
    pricing: str | None = None
    type: str | None = None
    # do inventário local (config.yaml)
    group: str | None = None
    modality: str | None = None
    # sondas de capacidade (nome -> {ok, evidence})
    probes: dict = field(default_factory=dict)
    # metadados de resposta observados (ex.: usage, finish_reason)
    observed: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def fetch_models(sender) -> list[dict]:
    """GET /models via sender; devolve a lista ``data`` (ou [])."""
    r = sender("/models", json_body=None)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return (r.json() or {}).get("data", [])


def make_getter(cfg: dict):
    """GET autenticado ao proxy (o sender padrão só faz POST)."""
    import requests

    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _get(path: str, **kwargs):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        return requests.get(url, headers=headers, timeout=60)

    return _get


def _probe(sender, path: str, body: dict, verdict) -> dict:
    """Roda uma sonda e devolve {ok, evidence, status, observed}."""
    try:
        r = sender(path, json_body=body)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "evidence": f"erro rede: {exc}", "status": None}
    if r.status_code != 200:
        return {"ok": False, "evidence": f"HTTP {r.status_code}: {r.text[:120]}",
                "status": r.status_code}
    try:
        resp = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "evidence": "resposta não-JSON", "status": 200}
    ok, ev = verdict(resp)
    out = {"ok": ok, "evidence": ev, "status": 200}
    # metadados observados (usage, finish_reason, dims) — informativo
    obs: dict = {}
    if isinstance(resp, dict):
        if resp.get("usage"):
            obs["usage"] = resp["usage"]
        if resp.get("model"):
            obs["model"] = resp["model"]
        ch = (resp.get("choices") or [{}])[0]
        if ch.get("finish_reason"):
            obs["finish_reason"] = ch["finish_reason"]
        data = resp.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            emb = data[0].get("embedding")
            if isinstance(emb, list):
                obs["embedding_dim"] = len(emb)
    if obs:
        out["observed"] = obs
    return out


def probe_chat(sender, model: str) -> dict:
    return _probe(sender, "/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Diga apenas: OK"}],
        "max_tokens": 64,
    }, N.verdict_chat)


def probe_thinking(sender, model: str) -> dict:
    return _probe(sender, "/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Quanto é 17*23? Responda só o número."}],
        "max_tokens": 512,
        "extra_body": {"thinking": {"type": "enabled"}},
    }, N.verdict_thinking_on)


def probe_tools(sender, model: str) -> dict:
    return _probe(sender, "/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Chame a função noop."}],
        "max_tokens": 128,
        "tools": [{"type": "function", "function": {
            "name": "noop", "description": "chame esta função",
            "parameters": {"type": "object", "properties": {}}}}],
        "tool_choice": "auto",
    }, N.verdict_tool_calls)


def probe_embedding(sender, model: str) -> dict:
    return _probe(sender, "/embeddings", {
        "model": model, "input": "teste de embedding",
    }, lambda resp: N.verdict_embeddings(resp))


def probe_image(sender, model: str) -> dict:
    return _probe(sender, "/images/generations", {
        "model": model, "prompt": "a red circle on white background", "n": 1,
    }, N.verdict_image)


def probe_tts(sender, model: str) -> dict:
    try:
        r = sender("/audio/speech", json_body={
            "model": model, "input": "teste", "voice": "alloy",
        })
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "evidence": f"erro rede: {exc}", "status": None}
    if r.status_code != 200:
        return {"ok": False, "evidence": f"HTTP {r.status_code}: {r.text[:120]}",
                "status": r.status_code}
    ok, ev = N.verdict_audio(r.content)
    return {"ok": ok, "evidence": ev, "status": 200}


def probe_asr(sender, model: str) -> dict:
    # ASR precisa de um arquivo de áudio; sem fixture, só registra que é ASR.
    return {"ok": False, "evidence": "requer arquivo de áudio (não sondado)",
            "status": None}


# modalidade (do inventário) -> sondas a rodar
PROBES_BY_MODALITY = {
    "chat": [("chat", probe_chat), ("thinking", probe_thinking), ("tools", probe_tools)],
    "chat-fast": [("chat", probe_chat), ("tools", probe_tools)],
    "embedding": [("embedding", probe_embedding)],
    "image": [("image", probe_image)],
    "tts": [("tts", probe_tts)],
    "asr": [("asr", probe_asr)],
}


def extract(sender, rows: list[dict], *, sleep: float = 0.0,
            progress=None, getter=None, novai_only: bool = False) -> list[ModelInfo]:
    """Monta um ModelInfo por modelo, cruzando /models com o inventário local.

    ``sender`` faz POST (sondas); ``getter`` faz GET (/models). Se ``getter``
    for None, usa ``sender`` (útil nos testes com rota única).
    ``novai_only`` restringe aos modelos presentes no inventário NovAI.
    """
    api_models = fetch_models(getter or sender)
    by_id = {m.get("id"): m for m in api_models}

    # agrupa o inventário por upstream_id (um modelo pode ter base + -fast)
    inv_by_upstream: dict[str, list[dict]] = {}
    for r in rows:
        inv_by_upstream.setdefault(r["upstream_id"], []).append(r)

    out: list[ModelInfo] = []
    ids = sorted(set(by_id) | set(inv_by_upstream))
    if novai_only:
        ids = [i for i in ids if i in inv_by_upstream]
    for i, mid in enumerate(ids):
        meta = by_id.get(mid, {})
        info = ModelInfo(
            id=mid,
            owned_by=meta.get("owned_by"),
            pricing=meta.get("pricing"),
            type=meta.get("type"),
        )
        inv_rows = inv_by_upstream.get(mid, [])
        if inv_rows:
            info.group = inv_rows[0]["group"]
            info.modality = inv_rows[0]["modality"]
        if progress:
            progress(i, len(ids), mid)
        if sleep > 0 and i > 0:
            time.sleep(sleep)
        # roda as sondas da modalidade (usa o group do proxy, não o id upstream)
        group = info.group or mid
        for name, fn in PROBES_BY_MODALITY.get(info.modality or "", []):
            try:
                info.probes[name] = fn(sender, group)
            except Exception as exc:  # noqa: BLE001
                info.errors.append(f"{name}: {type(exc).__name__}: {exc}")
        out.append(info)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--family", help="chat|embedding|image|tts|asr (filtra sondas)")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="pausa (s) entre modelos no modo --live")
    ap.add_argument("--novai-only", action="store_true",
                    help="só modelos do inventário NovAI (ignora modelos locais do proxy)")
    ap.add_argument("--live", action="store_true", help="de fato chama o proxy")
    args = ap.parse_args(argv)

    if not args.live:
        print("modo offline: use --live para consultar a API", file=sys.stderr)
        return 2

    cfg = N.proxy_config()
    sender = N.make_sender(cfg)
    getter = make_getter(cfg)
    rows = N.load_groups()
    if args.family:
        rows = N.select(rows, args.family, None)

    def _prog(i, n, mid):
        print(f"[{i+1}/{n}] {mid}", flush=True)

    infos = extract(sender, rows, sleep=args.sleep, progress=_prog, getter=getter,
                    novai_only=args.novai_only)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps([asdict(x) for x in infos], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n_probe = sum(len(x.probes) for x in infos)
    n_ok = sum(1 for x in infos for p in x.probes.values() if p.get("ok"))
    print(f"modelos={len(infos)} sondas={n_probe} ok={n_ok}")
    print(f"salvo: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
