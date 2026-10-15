"""Testes unitários do agregador de eventos do MCP (eval/mcp_report.py) — SEM rede.

Exercitam as funções puras: parse_line, aggregate, percentile, _latency_stats e
build_report (com line_source injetável). Nada aqui toca o log real.
"""

from __future__ import annotations

import json

from eval import mcp_report as mr


def _search(ts=1.0, repo="r", profile="qwen37", kind="code", latency=10.0,
            slo=200.0, breach=False, status="ok", n=3):
    return json.dumps({
        "event": "rag_search", "ts": ts, "repo": repo, "profile": profile,
        "query": "q", "k": 8, "kind": kind, "path_prefix": None, "n_results": n,
        "latency_ms": latency, "slo_ms": slo, "slo_breach": breach, "status": status,
    })


def _stale(ts=1.0, ms=5.0, stale=False):
    return json.dumps({"event": "rag_search_staleness", "ts": ts,
                       "staleness_ms": ms, "stale": stale})


# --- parse_line ------------------------------------------------------------

def test_parse_line_search():
    ev = mr.parse_line(_search(latency=42.5, breach=True))
    assert isinstance(ev, mr.SearchEvent)
    assert ev.latency_ms == 42.5
    assert ev.slo_breach is True
    assert ev.kind == "code"


def test_parse_line_staleness():
    ev = mr.parse_line(_stale(ms=7.5, stale=True))
    assert isinstance(ev, mr.StalenessEvent)
    assert ev.staleness_ms == 7.5
    assert ev.stale is True


def test_parse_line_ruido_retorna_none():
    assert mr.parse_line("") is None
    assert mr.parse_line("   ") is None
    assert mr.parse_line("não é json") is None
    assert mr.parse_line("[1,2,3]") is None  # JSON válido mas não-dict
    assert mr.parse_line('{"event": "outro"}') is None


def test_parse_line_campos_ausentes_tolerados():
    # evento mínimo: só o discriminador → defaults seguros, não levanta.
    ev = mr.parse_line('{"event": "rag_search"}')
    assert isinstance(ev, mr.SearchEvent)
    assert ev.latency_ms == 0.0
    assert ev.slo_ms == mr.SLO_LATENCY_MS
    assert ev.status == "ok"


def test_parse_line_tipo_invalido_retorna_none():
    # latency_ms não-numérico → ValueError capturado → None (não levanta).
    assert mr.parse_line('{"event": "rag_search", "latency_ms": "abc"}') is None
    # staleness_ms não-numérico → None.
    assert mr.parse_line('{"event": "rag_search_staleness", "staleness_ms": "x"}') is None


# --- aggregate -------------------------------------------------------------

def test_aggregate_separa_e_conta_malformed():
    lines = [_search(), _stale(), "ruído", "", _search(latency=300.0, breach=True)]
    rep = mr.aggregate(lines)
    assert len(rep.searches) == 2
    assert len(rep.staleness) == 1
    assert rep.malformed == 1  # só "ruído" (linha vazia não conta)


# --- percentile ------------------------------------------------------------

def test_percentile_vazio_e_zero():
    assert mr.percentile([], 0.5) == 0.0


def test_percentile_nearest_rank():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert mr.percentile(vals, 0.50) == 30.0
    assert mr.percentile(vals, 0.95) == 50.0


# --- _latency_stats --------------------------------------------------------

def test_latency_stats_conta_breaches():
    evs = [mr.SearchEvent(1, "r", "qwen37", "code", 100.0, 200.0, False, "ok", 3),
           mr.SearchEvent(2, "r", "qwen37", "code", 300.0, 200.0, True, "ok", 3)]
    s = mr._latency_stats(evs)
    assert s["calls"] == 2
    assert s["breaches"] == 1
    assert s["breach_rate"] == 0.5
    assert s["max"] == 300.0


def test_latency_stats_vazio():
    s = mr._latency_stats([])
    assert s["calls"] == 0
    assert s["breach_rate"] == 0.0
    assert s["max"] == 0.0


# --- build_report ----------------------------------------------------------

def test_build_report_renderiza_totais():
    lines = [_search(latency=100.0), _search(latency=300.0, breach=True)]
    md = mr.build_report(line_source=lambda: lines)
    assert "Chamadas | 2" in md
    assert "Breaches de SLO" in md
    assert "50.0%" in md  # 1 de 2


def test_build_report_vazio_nao_quebra():
    md = mr.build_report(line_source=lambda: [])
    assert "Nenhum evento" in md


def test_build_report_inclui_secao_staleness():
    lines = [_search(), _stale(ms=12.0, stale=True)]
    md = mr.build_report(line_source=lambda: lines)
    assert "staleness" in md.lower()
    assert "12.00 ms" in md


def test_build_report_inclui_erros():
    lines = [_search(status="error:EmbedError")]
    md = mr.build_report(line_source=lambda: lines)
    assert "Chamadas com erro" in md
    assert "error:EmbedError" in md


def test_build_report_agrupa_por_kind_e_profile():
    lines = [_search(kind="code"), _search(kind="doc"),
             _search(profile="bgem3")]
    md = mr.build_report(line_source=lambda: lines)
    assert "`code`" in md
    assert "`doc`" in md
    assert "`bgem3`" in md


# --- S90/B3: alerta de SLO -------------------------------------------------

def test_slo_alert_dispara_acima_do_limiar():
    # 2 de 2 em breach = 100% > 50% → alerta.
    rep = mr.aggregate([_search(latency=300.0, breach=True),
                        _search(latency=400.0, breach=True)])
    alert = mr.slo_alert(rep)
    assert alert is not None
    assert "ALERTA" in alert
    assert "100.0%" in alert


def test_slo_alert_silencia_abaixo_do_limiar():
    # 1 de 4 em breach = 25% < 50% → sem alerta.
    rep = mr.aggregate([_search(latency=300.0, breach=True),
                        _search(latency=10.0), _search(latency=10.0),
                        _search(latency=10.0)])
    assert mr.slo_alert(rep) is None


def test_slo_alert_vazio_nao_dispara():
    assert mr.slo_alert(mr.aggregate([])) is None


def test_slo_alert_limiar_customizado():
    # 1 de 2 = 50%; com limiar 40% dispara, com 60% não.
    rep = mr.aggregate([_search(latency=300.0, breach=True), _search(latency=10.0)])
    assert mr.slo_alert(rep, threshold_pct=40.0) is not None
    assert mr.slo_alert(rep, threshold_pct=60.0) is None


def test_main_emite_alerta_em_stderr(tmp_path, capsys):
    log = tmp_path / "mcp.log"
    log.write_text(_search(latency=500.0, breach=True) + "\n")
    rc = mr.main(["--log", str(log), "--out", str(tmp_path / "r.md")])
    assert rc == 0
    err = capsys.readouterr().err
    assert "ALERTA" in err


def test_main_sem_alerta_quando_ok(tmp_path, capsys):
    log = tmp_path / "mcp.log"
    log.write_text(_search(latency=10.0, breach=False) + "\n")
    rc = mr.main(["--log", str(log), "--out", str(tmp_path / "r.md")])
    assert rc == 0
    assert "ALERTA" not in capsys.readouterr().err


def test_read_lines_arquivo_ausente_vazio(tmp_path):
    assert mr._read_lines(str(tmp_path / "nao-existe.log")) == []


def test_main_sem_out_imprime_relatorio(tmp_path, capsys):
    log = tmp_path / "mcp.log"
    log.write_text(_search(latency=10.0) + "\n")
    rc = mr.main(["--log", str(log)])
    assert rc == 0
    assert "Relatório de latência" in capsys.readouterr().out


def test_build_report_log_inexistente_nao_quebra(tmp_path):
    md = mr.build_report(log_path=str(tmp_path / "nao-existe.log"))
    assert "Nenhum evento" in md
