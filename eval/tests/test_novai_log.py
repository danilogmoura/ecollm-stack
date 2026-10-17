"""Testes do log estruturado NovAI (eval/novai_log.py) — SEM rede, SEM disco real.

Aceitação travada (S103 / P3b): nenhum prefixo de chave sobrevive ao log.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from eval import novai_log as nl
from eval import novai_test as nt


def _cr(**kw):
    base = dict(group="novai-x", modality="chat", test="smoke", passed=True,
                evidence="ok")
    base.update(kw)
    return nt.CheckResult(**base)


def test_redact_novai_key():
    assert nl.redact("chave nvai-abc123XYZ") == "chave nvai-***REDACTED***"


def test_redact_sk_key():
    assert nl.redact("sk-abcdef123456") == "sk-***REDACTED***"


def test_redact_bearer_header():
    out = nl.redact("Authorization: Bearer sk-abcdef123456")
    assert "abcdef123456" not in out


def test_redact_is_idempotent():
    once = nl.redact("nvai-abc123XYZ")
    assert nl.redact(once) == once


def test_redact_leaves_plain_text():
    assert nl.redact("sem segredo aqui") == "sem segredo aqui"


def test_redact_empty():
    assert nl.redact("") == ""


def test_redact_obj_recurses():
    obj = {"a": ["nvai-abc123", {"b": "sk-zzz999"}], "n": 1}
    out = nl.redact_obj(obj)
    assert "abc123" not in json.dumps(out)
    assert "zzz999" not in json.dumps(out)
    assert out["n"] == 1


def test_log_path_format():
    when = datetime(2026, 10, 16, tzinfo=timezone.utc)
    p = nl.log_path("chat", when=when)
    assert p.name == "2026-10-16-novai-chat.jsonl"
    assert p.parent.name == "logs"


def test_log_path_sanitizes_family():
    when = datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert nl.log_path("chat/fast", when=when).name == "2026-10-16-novai-chat-fast.jsonl"


def test_result_to_record_fields():
    rec = nl.result_to_record(_cr(latency_ms=12.5, target="gateway"))
    assert rec["target"] == "gateway"
    assert rec["status"] == "pass"
    assert rec["latency_ms"] == 12.5
    assert rec["ts"].startswith("20")


def test_result_to_record_redacts_evidence():
    rec = nl.result_to_record(_cr(evidence="falhou com nvai-secret123"))
    assert "secret123" not in json.dumps(rec)


def test_write_records_appends_jsonl(tmp_path):
    p = tmp_path / "x.jsonl"
    nl.write_records([{"a": 1}], p)
    nl.write_records([{"a": 2}], p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(x)["a"] for x in lines] == [1, 2]


def test_log_results_skips_skipped(tmp_path):
    res = [_cr(), _cr(skipped=True, passed=False)]
    p = nl.log_results(res, family="chat", root=tmp_path)
    assert p is not None
    assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_log_results_none_when_all_skipped(tmp_path):
    assert nl.log_results([_cr(skipped=True)], family="chat", root=tmp_path) is None


def test_log_results_acceptance_no_key_prefix(tmp_path):
    """ACEITAÇÃO: grep do prefixo da chave no jsonl = 0 hits."""
    res = [_cr(evidence="erro 401 com nvai-REALKEY123456"),
           _cr(evidence="Bearer sk-REALKEY789", passed=False)]
    p = nl.log_results(res, family="chat", root=tmp_path)
    text = p.read_text(encoding="utf-8")
    assert "nvai-REALKEY123456" not in text
    assert "sk-REALKEY789" not in text
    assert "REALKEY" not in text
