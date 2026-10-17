"""Testes unitários do inventário NovAI (eval/novai_inventory.py) — SEM rede.

Exercitam as funções puras: classify() e parse_config() sobre um YAML mínimo
injetável, mais uma sanidade sobre o config real do repo (contagens travadas).
Nada aqui chama o proxy nem gasta saldo.
"""

from __future__ import annotations

from pathlib import Path

from eval import novai_inventory as ni

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CONFIG = REPO_ROOT / "litellm" / "config.yaml"

MINI_YAML = """\
model_list:
  - model_name: novai-glm-4.6
    litellm_params:
      model: openai/glm-4.6
  - model_name: novai-glm-4.6-fast
    litellm_params:
      model: openai/glm-4.6
  - model_name: novai-embed-text-embedding-v4
    litellm_params:
      model: openai/text-embedding-v4
  - model_name: novai-image-cogview-3-flash
    litellm_params:
      model: openai/cogview-3-flash
  - model_name: novai-tts-qwen-tts
    litellm_params:
      model: openai/qwen-tts
  - model_name: novai-asr-wand-asr-v1
    litellm_params:
      model: openai/wand-asr-v1
  - model_name: qwen3.8-max
    litellm_params:
      model: hosted_vllm/qwen3.8-max
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
"""


# --- classify --------------------------------------------------------------

def test_classify_chat_on_off():
    assert ni.classify("novai-glm-4.6") == "chat"
    assert ni.classify("novai-glm-4.6-fast") == "chat-fast"


def test_classify_nonchat_prefixes():
    assert ni.classify("novai-embed-x") == "embedding"
    assert ni.classify("novai-image-x") == "image"
    assert ni.classify("novai-tts-x") == "tts"
    assert ni.classify("novai-asr-x") == "asr"


def test_classify_video_in_chat_name_is_not_passthrough():
    # hunyuan-turbos-vision-video é CHAT (prefixo família), não vídeo roteável.
    assert ni.classify("novai-hunyuan-turbos-vision-video") == "chat"


# --- parse_config ----------------------------------------------------------

def test_parse_config_mini():
    rows = ni.parse_config(MINI_YAML)
    by_group = {r["group"]: r for r in rows}
    # o grupo não-novai (qwen3.8-max) NÃO entra.
    assert "qwen3.8-max" not in by_group
    assert len(rows) == 6
    assert by_group["novai-glm-4.6"]["modality"] == "chat"
    assert by_group["novai-glm-4.6"]["upstream_id"] == "glm-4.6"  # prefixo openai/ removido
    assert by_group["novai-embed-text-embedding-v4"]["modality"] == "embedding"


def test_parse_config_stops_at_top_level_key():
    rows = ni.parse_config(MINI_YAML)
    # general_settings não deve introduzir linhas extras.
    assert all(r["group"].startswith("novai-") for r in rows)


# --- sanidade sobre o config real (contagens travadas S100/S102) -----------

def test_real_config_counts_locked():
    if not REAL_CONFIG.exists():
        raise AssertionError(f"config esperado ausente: {REAL_CONFIG}")
    rows = ni.parse_config(REAL_CONFIG.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["modality"]] = counts.get(r["modality"], 0) + 1
    assert len(rows) == 155
    assert counts["chat"] == 61
    assert counts["chat-fast"] == 61
    assert counts["embedding"] == 6
    assert counts["image"] == 14
    assert counts["tts"] == 11
    assert counts["asr"] == 2


def test_passthrough_entries_are_two():
    mods = {p["modality"] for p in ni.PASSTHROUGH}
    assert mods == {"video-passthrough", "3d-passthrough"}


def test_matrix_csv_has_new_columns_after_legacy_prefix(tmp_path):
    """S103 / P3: as 5 colunas da Fase A ficam no MESMO índice; novas vão no fim."""
    import csv

    from eval import novai_inventory as ni

    out = tmp_path / "m.csv"
    assert ni.main(["--out", str(out)]) == 0
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    assert header[:5] == ["group", "modality", "upstream_id", "status", "evidence"]
    assert header[5:] == ["target", "test_id", "latency_ms", "notes"]
    assert all(len(r) == len(header) for r in rows[1:])
    assert all(r[3] == "untested" for r in rows[1:])


def test_regenerate_preserves_existing_results(tmp_path):
    """S103 / P3: regenerar o inventário NUNCA apaga resultado de run."""
    import csv

    from eval import novai_inventory as ni

    out = tmp_path / "m.csv"
    assert ni.main(["--out", str(out)]) == 0
    # simula um run que marcou 2 grupos
    with out.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[1][3], rows[1][4] = "pass", "chat: OK"
    rows[2][3], rows[2][4] = "fail", "chat: HTTP 404"
    with out.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)

    assert ni.main(["--out", str(out)]) == 0
    with out.open(encoding="utf-8", newline="") as fh:
        after = list(csv.reader(fh))
    assert after[1][3] == "pass" and after[1][4] == "chat: OK"
    assert after[2][3] == "fail" and after[2][4] == "chat: HTTP 404"
    assert after[0][:5] == ["group", "modality", "upstream_id", "status", "evidence"]
