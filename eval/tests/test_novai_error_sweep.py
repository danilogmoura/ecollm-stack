"""Testes do sweep de contrato de erro (S115) — puros, sem rede."""

from __future__ import annotations

import json

from eval import novai_error_sweep as es
from eval.novai_test import CheckResult


# ---------------------------------------------------------------------------
# envelope_class — classificação do shape de erro
# ---------------------------------------------------------------------------


def test_envelope_openai_shape():
    body = json.dumps({"error": {"message": "Invalid model name"}})
    assert es.envelope_class(body) == "openai"


def test_envelope_openai_error_as_string():
    assert es.envelope_class(json.dumps({"error": "boom"})) == "openai"


def test_envelope_fastapi_detail_string():
    body = json.dumps({"detail": "Model 'x' not supported"})
    assert es.envelope_class(body) == "fastapi"


def test_envelope_fastapi_detail_dict():
    assert es.envelope_class(json.dumps({"detail": {"message": "bad"}})) == "fastapi"


def test_envelope_both_fields():
    body = json.dumps({"error": {"message": "a"}, "detail": "b"})
    assert es.envelope_class(body) == "both"


def test_envelope_other_when_no_known_field():
    assert es.envelope_class(json.dumps({"foo": "bar"})) == "other"


def test_envelope_other_when_not_a_dict():
    assert es.envelope_class(json.dumps(["a", "b"])) == "other"


def test_envelope_other_when_invalid_json():
    assert es.envelope_class("<html>502 Bad Gateway</html>") == "other"


def test_envelope_empty_when_blank():
    assert es.envelope_class("") == "empty"
    assert es.envelope_class("   \n ") == "empty"


# ---------------------------------------------------------------------------
# summarize — agregação por (target, test_id)
# ---------------------------------------------------------------------------


def _res(target: str, test: str, passed: bool) -> CheckResult:
    return CheckResult("g", "chat", test, passed, "ev", target=target)


def test_summarize_counts_pass_and_fail():
    results = [
        _res("proxy", "error_404", True),
        _res("proxy", "error_404", False),
        _res("gateway", "error_404", True),
    ]
    classes = {("proxy", "error_404"): "openai", ("gateway", "error_404"): "fastapi"}
    out = es.summarize(results, classes)
    assert out[("proxy", "error_404")] == {"pass": 1, "fail": 1, "env:openai": 1}
    assert out[("gateway", "error_404")] == {"pass": 1, "env:fastapi": 1}


def test_summarize_without_class_omits_env_key():
    out = es.summarize([_res("proxy", "error_400", True)], {})
    assert out[("proxy", "error_400")] == {"pass": 1}


def test_summarize_empty_results():
    assert es.summarize([], {}) == {}
