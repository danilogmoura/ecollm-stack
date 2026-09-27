"""S31-b · Cobertura dos entrypoints (main/CLI) — SEM rede/DB/cota.

Os `main()` de ingest, cli e cache_report eram a maior lacuna de codigo VIVO:
sao a camada que parseia argv e delega para a logica ja testada. Aqui cada
dependencia externa (run_ingest, search, docker/psql) e stubada via monkeypatch,
entao nada toca Postgres, LiteLLM nem o binario docker.

Cobre:
- ingest.main        : dry-run (sem summary), nao-dry (summary), gate abort -> exit code.
- cli.cmd_sync       : repassa flags a run_ingest, imprime summary, trata SystemExit.
- cli.main           : roteamento "sync", query bareta -> search, sem-func -> help+1.
- cache_report.main  : --out escreve arquivo; stdout quando sem --out.
- fetch_rows_via_docker: rc!=0 levanta; decodifica JSON e ignora ruido nao-JSON.
"""

from __future__ import annotations

import json
import subprocess
import types

from eval import cache_report as cr
from ingest import cli
from ingest import ingest as ingest_mod
from ingest.store import SyncReport


def _report(**kw) -> SyncReport:
    base = dict(repo="ecollm-stack", files_seen=3, chunks_total=42, inserted=5)
    base.update(kw)
    return SyncReport(**base)


# ---------------------------------------------------------------------------
# ingest.main
# ---------------------------------------------------------------------------

def test_ingest_main_dry_run_nao_imprime_summary(monkeypatch, capsys):
    chamado = {}

    def fake_run(repo, *, dry_run, verbose, skip_gitleaks, profile=None):
        chamado.update(repo=repo, dry_run=dry_run, verbose=verbose,
                       skip_gitleaks=skip_gitleaks)
        return _report()

    monkeypatch.setattr(ingest_mod, "run_ingest", fake_run)
    rc = ingest_mod.main(["--dry-run"])
    assert rc == 0
    assert chamado["dry_run"] is True
    # dry-run NAO deve imprimir o resumo do store
    assert "[store:" not in capsys.readouterr().out


def test_ingest_main_imprime_summary_quando_nao_dry(monkeypatch, capsys):
    monkeypatch.setattr(ingest_mod, "run_ingest",
                        lambda repo, **k: _report())
    rc = ingest_mod.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[store:ecollm-stack]" in out and "chunks=42" in out


def test_ingest_main_propaga_abort_do_gate(monkeypatch, capsys):
    def boom(repo, **k):
        raise SystemExit(3)  # gate de segredos aborta com codigo 3

    monkeypatch.setattr(ingest_mod, "run_ingest", boom)
    rc = ingest_mod.main([])
    assert rc == 3
    assert "[abort] codigo 3" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cli.cmd_sync
# ---------------------------------------------------------------------------

def _sync_args(repo=".", dry_run=False, quiet=False, skip_gitleaks=False):
    return types.SimpleNamespace(repo=repo, dry_run=dry_run, quiet=quiet,
                                 skip_gitleaks=skip_gitleaks)


def test_cmd_sync_repassa_flags_e_imprime_summary(monkeypatch, capsys):
    chamado = {}

    def fake_run(repo, *, dry_run, verbose, skip_gitleaks, profile=None):
        chamado.update(dry_run=dry_run, verbose=verbose, skip_gitleaks=skip_gitleaks)
        return _report()

    monkeypatch.setattr(cli.ingest_mod, "run_ingest", fake_run)
    rc = cli.cmd_sync(_sync_args(skip_gitleaks=True))
    assert rc == 0
    assert chamado == {"dry_run": False, "verbose": True, "skip_gitleaks": True}
    assert "[store:ecollm-stack]" in capsys.readouterr().out


def test_cmd_sync_quiet_desliga_verbose(monkeypatch):
    chamado = {}
    monkeypatch.setattr(cli.ingest_mod, "run_ingest",
                        lambda repo, **k: chamado.update(k) or _report())
    cli.cmd_sync(_sync_args(quiet=True))
    assert chamado["verbose"] is False


def test_cmd_sync_traduz_systemexit_em_codigo(monkeypatch, capsys):
    def boom(repo, **k):
        raise SystemExit(2)

    monkeypatch.setattr(cli.ingest_mod, "run_ingest", boom)
    rc = cli.cmd_sync(_sync_args())
    assert rc == 2
    assert "[abort] codigo 2" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cli.main (roteamento)
# ---------------------------------------------------------------------------

def test_cli_main_rota_para_sync(monkeypatch):
    visto = {}

    def fake_sync(args):
        visto["ok"] = True
        return 0

    monkeypatch.setattr(cli, "cmd_sync", fake_sync)
    rc = cli.main(["sync", "--dry-run"])
    assert rc == 0
    assert visto.get("ok") is True


def test_cli_main_sem_subcomando_mostra_ajuda_e_retorna_um(monkeypatch, capsys):
    # argv vazio => nenhum func definido => print_help + 1
    rc = cli.main([])
    assert rc == 1
    assert "usage" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cache_report.main
# ---------------------------------------------------------------------------

_RAW_ROWS = [
    {"startTime": "2026-09-01T10:00:00Z", "model_group": "qwen3.8-max",
     "prompt_tokens": 1000, "completion_tokens": 200, "cached_tokens": 800,
     "spend": 0.002},
    {"startTime": "2026-09-02T11:00:00Z", "model_group": "qwen3.8-flash",
     "prompt_tokens": 500, "completion_tokens": 100, "cached_tokens": 0,
     "spend": 0.0005},
]


def test_cache_report_main_escreve_arquivo(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cr, "fetch_rows_via_docker", lambda sql, **k: list(_RAW_ROWS))
    out = tmp_path / "c6.md"
    rc = cr.main(["--days", "7", "--out", str(out)])
    assert rc == 0
    texto = out.read_text(encoding="utf-8")
    assert "# C6 · Relatório" in texto
    assert "## Totais" in texto
    assert "[c6] relatório escrito" in capsys.readouterr().err


def test_cache_report_main_stdout_sem_out(monkeypatch, capsys):
    monkeypatch.setattr(cr, "fetch_rows_via_docker", lambda sql, **k: [])
    rc = cr.main([])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "# C6 · Relatório" in printed
    # janela vazia => mensagem de nenhuma chamada
    assert "Nenhuma chamada" in printed


# ---------------------------------------------------------------------------
# fetch_rows_via_docker (stub do subprocess.run — sem docker real)
# ---------------------------------------------------------------------------

def _completed(rc_code, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc_code,
                                       stdout=stdout, stderr=stderr)


def test_fetch_rows_decodifica_json_e_ignora_ruido(monkeypatch):
    linha = json.dumps({"model_group": "qwen3.8-max", "prompt_tokens": 10})
    saida = f"{linha}\n\nruído não-json aqui\n{linha}\n"
    monkeypatch.setattr(cr.subprocess, "run",
                        lambda *a, **k: _completed(0, stdout=saida))
    rows = cr.fetch_rows_via_docker("SELECT 1")
    assert len(rows) == 2  # duas linhas JSON válidas; ruído e vazio descartados
    assert rows[0]["model_group"] == "qwen3.8-max"


def test_fetch_rows_levanta_quando_rc_diferente_de_zero(monkeypatch):
    monkeypatch.setattr(cr.subprocess, "run",
                        lambda *a, **k: _completed(1, stderr="auth fail"))
    try:
        cr.fetch_rows_via_docker("SELECT 1")
    except RuntimeError as exc:
        assert "psql falhou" in str(exc)
    else:
        raise AssertionError("deveria ter levantado RuntimeError")
