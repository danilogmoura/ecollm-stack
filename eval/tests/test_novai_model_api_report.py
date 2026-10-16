"""Testes offline do gerador de relatório de metadados por modelo."""
from __future__ import annotations

from eval.novai_model_api_report import _probe_cell, build

MODELS = [
    {
        "id": "glm-5", "owned_by": "zhipu", "pricing": "paid", "type": None,
        "group": "novai-glm-5", "modality": "chat",
        "probes": {
            "chat": {"ok": True, "evidence": "finish=stop len(content)=2", "status": 200},
            "tools": {"ok": False, "evidence": "sem tool_calls", "status": 200},
        },
        "observed": {}, "errors": [],
    },
    {
        "id": "kinfra-text-embedding-4b", "owned_by": "tencent", "pricing": None,
        "type": None, "group": "novai-kinfra-text-embedding-4b",
        "modality": "embedding",
        "probes": {"embedding": {"ok": True, "evidence": "dim=2560", "status": 200}},
        "observed": {}, "errors": [],
    },
]


def test_probe_cell_ok_and_fail():
    assert _probe_cell({"ok": True, "evidence": "x"}).startswith("✅")
    assert _probe_cell({"ok": False, "evidence": "y"}).startswith("❌")
    assert _probe_cell(None) == "—"


def test_probe_cell_truncates_long_evidence():
    cell = _probe_cell({"ok": True, "evidence": "a" * 200})
    assert len(cell) < 80
    assert cell.endswith("…")


def test_build_has_title_and_counts():
    md = build(MODELS)
    assert "# NovAI — Metadados por modelo (via API)" in md
    assert "Modelos: **2**" in md


def test_build_summary_by_modality():
    md = build(MODELS)
    assert "| chat | 1 |" in md
    assert "| embedding | 1 |" in md


def test_build_probe_success_table():
    md = build(MODELS)
    assert "| chat | 1 | 1 |" in md
    assert "| tools | 0 | 1 |" in md


def test_build_detail_per_model():
    md = build(MODELS)
    assert "### `glm-5`" in md
    assert "owned_by: `zhipu`" in md
    assert "grupo: `novai-glm-5`" in md
    assert "### `kinfra-text-embedding-4b`" in md


def test_build_empty_models():
    md = build([])
    assert "Modelos: **0**" in md
