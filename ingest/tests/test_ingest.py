"""Testes da FASE 2 — ingest.py (orquestrador), com git real + embed/store fake.

Nao tocam LiteLLM nem pgvector: gitleaks/embed sao stubados e o "DB" e um dict
em memoria que imita existing_file_hashes/upsert/delete. O objetivo e validar a
MAQUINA de sync incremental (new/changed/unchanged/removido) e o --dry-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingest import embed, ingest, store
from ingest.tests.conftest import FakeDB, _git  # noqa: F401  (fixtures repo/patched no conftest)

# Gate real capturado ANTES de qualquer monkeypatch (os testes que exercitam o
# caminho fail-closed/skip restauram este callable, não o stub do fixture).
_REAL_GITLEAKS_GATE = ingest.gitleaks_gate


def test_primeira_execucao_inserta_tudo(repo, patched):
    rep = ingest.run_ingest(repo, verbose=False)
    assert rep.inserted > 0
    assert rep.deleted == 0
    assert rep.chunks_total == rep.inserted
    # conteudo embedado NAO contem task-prefix (prefixo so na chamada de embed,
    # mas embed_documents recebe texto puro + kind; aqui validamos que nao vazou)
    assert all(not t.startswith(embed.TASK_PREFIX_DOC) for t, _ in patched.embedded)


def test_reexecucao_sem_mudanca_zero_embeddings(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    patched.embedded.clear()
    rep2 = ingest.run_ingest(repo, verbose=False)
    assert patched.embedded == []          # nada re-embedado (blob igual)
    assert rep2.inserted == 0
    assert rep2.unchanged > 0


def test_arquivo_editado_reembeda_so_ele(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    patched.embedded.clear()
    (repo / "hello.py").write_text("def greet():\n    return 'hello world'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    rep = ingest.run_ingest(repo, verbose=False)
    # só hello.py foi re-embedado
    paths_embedded = {c for c in patched.embedded}
    assert rep.changed_files == ["hello.py"]
    assert rep.deleted >= 1  # chunk antigo de hello.py removido
    assert rep.inserted >= 1


def test_arquivo_apagado_remove_chunks(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    total_before = patched.count("myrepo")
    (repo / "notes.md").unlink()
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "rm")
    rep = ingest.run_ingest(repo, verbose=False)
    assert "notes.md" in rep.removed_files
    assert rep.deleted >= 1
    assert patched.count("myrepo") < total_before


def test_dry_run_nao_escreve_nem_embeda(repo, patched):
    rep = ingest.run_ingest(repo, dry_run=True, verbose=False)
    assert patched.embedded == []
    assert patched.count("myrepo") == 0
    assert rep.inserted == 0


def test_gate_falha_aborta(repo, monkeypatch):
    monkeypatch.setattr(ingest, "gitleaks_gate", lambda root, entries, *, skip=False: (False, "segredo!"))
    monkeypatch.setattr(store, "connect", lambda url=None: pytest.fail("não deveria conectar"))
    with pytest.raises(SystemExit) as exc:
        ingest.run_ingest(repo, verbose=False)
    assert exc.value.code == 2


# --- S13 · gate gitleaks FAIL-CLOSED -------------------------------------

def _no_gitleaks(monkeypatch):
    """Faz o gate NÃO encontrar o binário em lugar nenhum."""
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    monkeypatch.setattr(ingest.os.path, "isfile", lambda p: False)


def test_gate_binario_ausente_aborta_fail_closed(repo, monkeypatch):
    """Sem binário e sem permissão explícita => ABORTA (fail-closed)."""
    _no_gitleaks(monkeypatch)
    monkeypatch.delenv("RAG_SKIP_GITLEAKS", raising=False)
    ok, msg = ingest.gitleaks_gate(repo, [])
    assert ok is False
    assert "fail-closed" in msg


def test_gate_binario_ausente_passa_com_flag_skip(repo, monkeypatch):
    """Binário ausente + skip=True => passa com AVISO (decisão do operador)."""
    _no_gitleaks(monkeypatch)
    ok, msg = ingest.gitleaks_gate(repo, [], skip=True)
    assert ok is True
    assert "PULADO" in msg and "AVISO" in msg


def test_run_ingest_env_skip_deixa_passar(repo, patched, monkeypatch, capsys):
    """Env RAG_SKIP_GITLEAKS=1 faz o orquestrador aceitar binário ausente."""
    # patched stub o gate; restauramos o gate REAL (capturado antes do stub) e
    # forçamos binário ausente p/ exercitar o caminho fail-closed/skip.
    monkeypatch.setattr(ingest, "gitleaks_gate", _REAL_GITLEAKS_GATE)
    _no_gitleaks(monkeypatch)
    monkeypatch.setenv("RAG_SKIP_GITLEAKS", "1")
    ingest.run_ingest(repo, dry_run=True, verbose=True)
    out = capsys.readouterr().out
    assert "PULADO" in out


def test_run_ingest_sem_skip_aborta_pelo_env(repo, patched, monkeypatch):
    """Sem env nem flag, binário ausente aborta o orquestrador inteiro (exit 2)."""
    monkeypatch.setattr(ingest, "gitleaks_gate", _REAL_GITLEAKS_GATE)
    _no_gitleaks(monkeypatch)
    monkeypatch.delenv("RAG_SKIP_GITLEAKS", raising=False)
    with pytest.raises(SystemExit) as exc:
        ingest.run_ingest(repo, dry_run=True, verbose=False)
    assert exc.value.code == 2


def test_gate_segredo_aborta_mesmo_com_skip(repo, monkeypatch):
    """skip só cobre binário faltando; segredo ACHADO aborta sempre."""
    # Binário presente que retorna código != 0 (achou segredo).
    monkeypatch.setattr(ingest.shutil, "which", lambda name: "/usr/bin/gitleaks")
    monkeypatch.setattr(ingest.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "leak", "stderr": ""})())
    ok, msg = ingest.gitleaks_gate(repo, [], skip=True)
    assert ok is False
    assert "ACHOU segredo" in msg
