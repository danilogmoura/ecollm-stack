"""Testes unitarios do chunker (FASE 1 — PLANO-RAG §3).

Garantem os invariantes do plano:
  - nenhum chunk passa do teto de 512 tokens aprox.
  - funcao/classe de topo = unidade de corte (code)
  - definicao longa > cap e janela com partes rotuladas symbol#N
  - secoes de doc pequenas fundem na anterior; grandes explodem em partes com sobreposicao
  - chaves de config de tamanho razoavel permanecem separadas
Sem fixtures em disco: entradas inline, deterministas.
"""

from ingest import chunker


# ---------------------------------------------------------------------------
# code
# ---------------------------------------------------------------------------

def test_code_uma_funcao_curta_um_chunk():
    src = "def a(x):\n    return x\n"
    chunks = chunker.chunk_code("m.py", "python", src)
    assert len(chunks) == 1
    assert chunks[0].symbol == "a"
    assert "def a" in chunks[0].content


def test_code_funcao_e_classe_separadas():
    src = (
        "def greet(name):\n"
        + "".join(f"    print('linha {i} de saida para teste')\n" for i in range(20))
        + "\n\nclass Widget:\n"
        + "".join(f"    attr_{i} = {i}\n" for i in range(20))
    )
    syms = [c.symbol for c in chunker.chunk_code("m.py", "python", src)]
    assert "greet" in syms and "Widget" in syms


def test_code_funcao_longa_explode_em_partes_rotuladas():
    # ~900 tokens estimados (len/4), bem acima do cap de 512
    src = "def big():\n" + "".join(f"    x{i} = {i}  # comentario util\n" for i in range(400))
    chunks = chunker.chunk_code("m.py", "python", src)
    assert len(chunks) >= 2
    assert all(c.approx_tokens <= chunker.CODE_CAP_TOK for c in chunks)
    assert chunks[0].symbol.startswith("big")
    # simbolos numerados para nao colidir no banco
    assert chunks[1].symbol != chunks[0].symbol


def test_code_funcoes_minusculas_fundem_sem_perder_conteudo():
    src = "def a(x):\n    return x\n\ndef b(y):\n    return y\n"
    chunks = chunker.chunk_code("m.py", "python", src)
    assert len(chunks) == 1
    body = chunks[0].content
    assert "def a" in body and "def b" in body


def test_code_orfaos_fora_das_definicoes_sao_preservados():
    src = (
        "CONST = 42\n"
        "LISTA = [\n    1,\n    2,\n]\n\n\n"
        "def sozinha():\n    return CONST\n"
    )
    chunks = chunker.chunk_code("m.py", "python", src)
    joined = "\n".join(c.content for c in chunks)
    assert "CONST = 42" in joined
    assert "def sozinha" in joined


def test_code_nunca_ultrapassa_teto_de_tokens():
    src = "def f():\n" + "".join(f"    v = {i}\n" for i in range(1000))
    for c in chunker.chunk_code("m.py", "python", src):
        assert c.approx_tokens <= chunker.CODE_CAP_TOK


# ---------------------------------------------------------------------------
# doc
# ---------------------------------------------------------------------------

def test_doc_divide_por_h2():
    src = "# Titulo\n\n## Alpha\n\nconteudo alpha\n\n## Beta\n\nconteudo beta\n"
    syms = [c.symbol for c in chunker.chunk_doc("d.md", src)]
    assert "Alpha" in syms and "Beta" in syms


def test_doc_secao_miniscula_funde_na_anterior():
    src = "# T\n\n## A\n\n" + ("palavra. " * 60) + "\n\n## B\n\ncurta.\n"
    chunks = chunker.chunk_doc("d.md", src)
    corpo_a = [c for c in chunks if c.symbol == "A"]
    assert len(corpo_a) == 1
    assert "curta." in corpo_a[0].content  # B foi absorvido por A


def test_doc_secao_grande_explode_com_sobreposicao():
    corpo = "\n".join(f"linha de texto numerada {i} para ocupar espaco" for i in range(400))
    src = f"# T\n\n## S\n\n{corpo}\n"
    chunks = [c for c in chunker.chunk_doc("d.md", src) if c.symbol and c.symbol.startswith("S")]
    assert len(chunks) >= 2
    assert all(c.approx_tokens <= chunker.DOC_MAX_TOK for c in chunks)
    # partes rotuladas (1), (2)...
    assert chunks[0].symbol.endswith("(1)")
    # sobreposicao: ultimo trecho da parte 1 aparece no inicio da parte 2
    tail = chunks[0].content[-40:]
    assert tail.strip().splitlines()[-1] in chunks[1].content


def test_doc_tabela_fica_inteira_na_secao():
    tabela = "| a | b |\n|---|---|\n" + "\n".join(f"| {i} | {i*2} |" for i in range(30))
    src = f"# T\n\n## Ref\n\nintro.\n\n{tabela}\n"
    chunks = [c for c in chunker.chunk_doc("d.md", src) if c.symbol == "Ref"]
    assert len(chunks) == 1
    assert "| a | b |" in chunks[0].content
    assert chunks[0].content.count("|---|") == 1  # tabela nao cortada/duplicada


def test_doc_prepara_quebra_de_linha_unica_gigante():
    # paragrafo de linha unica > teto (minificado): deve rachar sem estourar o cap
    src = "# T\n\n## S\n\n" + ("x" * 4000) + "\n"
    chunks = [c for c in chunker.chunk_doc("d.md", src) if c.symbol and c.symbol.startswith("S")]
    assert len(chunks) >= 2
    assert all(c.approx_tokens <= chunker.DOC_MAX_TOK for c in chunks)


# ---------------------------------------------------------------------------
# S19 — âncora "path > heading" no conteúdo de chunks doc
# ---------------------------------------------------------------------------

def test_doc_ancora_path_heading_no_topo():
    src = "# T\n\n## Gotchas\n\ntexto da secao de gotchas.\n"
    ch = [c for c in chunker.chunk_doc("README.md", src) if c.symbol == "Gotchas"][0]
    assert ch.content.splitlines()[0] == "README.md > Gotchas"
    # corpo original preservado logo abaixo da âncora
    assert "texto da secao de gotchas." in ch.content


def test_doc_ancora_nao_duplica_em_reprocessamento():
    src = "# T\n\n## Sec\n\nconteudo.\n"
    once = [c for c in chunker.chunk_doc("a.md", src) if c.symbol == "Sec"][0].content
    twice = chunker._anchor_doc("a.md", "Sec", once)  # re-aplicar não deve repetir
    assert twice == once
    assert twice.count("a.md > Sec") == 1


def test_doc_sem_heading_nao_recebe_ancora():
    # preâmbulo antes do primeiro ## (symbol None) fica intacto
    src = "intro solta sem titulo\n\n## A\n\naaa\n"
    pre = [c for c in chunker.chunk_doc("d.md", src) if c.symbol is None]
    for c in pre:
        assert ">" not in c.content.splitlines()[0]


def test_doc_ancora_presente_em_cada_parte_grande():
    corpo = "\n".join(f"linha numerada {i} ocupando espaco valido" for i in range(400))
    src = f"# T\n\n## S\n\n{corpo}\n"
    parts = [c for c in chunker.chunk_doc("d.md", src)
             if c.symbol and c.symbol.startswith("S")]
    assert len(parts) >= 2
    for p in parts:
        # cada parte carrega a âncora com o título rotulado daquela parte
        assert p.content.splitlines()[0].startswith("d.md > S")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def test_config_yaml_chaves_grandes_separam():
    src = "\n".join(
        f"key{i}:\n" + "\n".join(f"  sub{j}: valor-{i}-{j}" for j in range(15)) + "\n"
        for i in range(3)
    )
    chunks = chunker.chunk_config("c.yaml", "yaml", src)
    assert [c.symbol for c in chunks] == ["key0", "key1", "key2"]


def test_config_yaml_chaves_minusculas_fundem():
    src = "a: 1\nb: 2\nc: 3\n"
    chunks = chunker.chunk_config("c.yaml", "yaml", src)
    assert len(chunks) == 1
    for k in ("a:", "b:", "c:"):
        assert k in chunks[0].content


def test_config_yaml_aninhado_mantém_subarvore_junta():
    src = (
        "models:\n"
        "  - name: rag-chat\n"
        "    litellm_params:\n"
        "      model: gemini/x\n"
        "      api_key: os.environ/K\n"
        "      timeout: 30\n"
        "      max_retries: 2\n"
        "      num_ctx: 4096\n"
        "      temperature: 0.2\n"
        "      top_p: 0.9\n"
        "      stop: []\n"
        "      extra: aaa-bbb-ccc\n"
        "      drop_params: true\n"
        "other:\n"
        "  z: 1\n"
    )
    chunks = chunker.chunk_config("c.yaml", "yaml", src)
    models = [c for c in chunks if c.symbol == "models"]
    assert len(models) == 1
    assert "drop_params" in models[0].content  # sub-arvore inteira no mesmo chunk


def test_config_toml_sections():
    src = (
        "[section-one]\n"
        + "\n".join(f'chave_{i} = "valor-{i}-com-texto-extra"' for i in range(15))
        + "\n\n[section-two]\n"
        + "\n".join(f'outra_{i} = "valor-{i}-com-texto-extra"' for i in range(15))
        + "\n"
    )
    chunks = chunker.chunk_config("c.toml", "toml", src)
    assert [c.symbol for c in chunks] == ["section-one", "section-two"]


# ---------------------------------------------------------------------------
# fachada
# ---------------------------------------------------------------------------

def test_chunk_file_facade_rota_por_kind():
    src = "def a(x):\n    return x\n"
    out = chunker.chunk_file("m.py", "code", "python", src)
    assert out and out[0].kind == "code"
    out = chunker.chunk_file("d.md", "doc", None, "# T\n\n## A\n\ntexto\n")
    assert out and out[0].kind == "doc"
    out = chunker.chunk_file("c.yml", "config", "yaml", "a: 1\n")
    assert out and out[0].kind == "config"


# ---------------------------------------------------------------------------
# S82 — cobertura dos ramos de borda (gaps identificados na auditoria)
# ---------------------------------------------------------------------------

def test_code_sem_gramatica_janela_orfa():
    """lang desconhecida → janela órfã de 400 tok (linha 125-129)."""
    src = "linha solta\n" * 200
    out = chunker.chunk_code("x.xyz", "unknown", src)
    assert out and all(c.symbol is None for c in out)
    assert all(c.approx_tokens <= chunker.CODE_WINDOW_TOK + 1 for c in out)


def test_code_arquivo_vazio_retorna_vazio():
    """source vazio → [] (não janela órfã)."""
    assert chunker.chunk_code("x.py", "python", "") == []
    assert chunker.chunk_code("x.py", "python", "   \n  ") == []


def test_code_leftover_gigante_quebra_em_janelas():
    """leftover (fora de definições) > 400 tok → janelas (linha 199-200)."""
    # imports/constantes soltas gigantes (não são definições)
    src = "\n".join(f"X{i} = {i}" for i in range(300))
    out = chunker.chunk_code("x.py", "python", src)
    assert out
    assert all(c.approx_tokens <= chunker.CODE_WINDOW_TOK + 1 for c in out)


def test_code_merge_absorve_minusculo_quando_anterior_pequeno():
    """Ramo 'anterior estava minúsculo: absorve este' (linha 212-213)."""
    # duas funções minúsculas seguidas → a 2ª é absorvida pela 1ª
    src = "def a():\n    pass\n\ndef b():\n    pass\n"
    out = chunker.chunk_code("x.py", "python", src)
    # ambas minúsculas → fundem num só chunk
    assert len(out) == 1
    assert "def a" in out[0].content and "def b" in out[0].content


def test_doc_fence_nao_quebra_heading_dentro_de_codigo():
    """Heading dentro de ``` não é tratado como seção (fence, linha 243)."""
    src = "# T\n\n## A\n\n```\n## nao-e-heading\n```\n\ntexto\n"
    out = chunker.chunk_doc("d.md", src)
    # '## nao-e-heading' está dentro do fence → NÃO vira seção
    titles = [c.symbol for c in out]
    assert not any("nao-e-heading" in (t or "") for t in titles)


def test_doc_sem_heading_retorna_um_chunk():
    """Doc sem heading → 1 chunk (sem âncora)."""
    out = chunker.chunk_doc("d.md", "texto puro sem heading\n" * 5)
    assert len(out) == 1
    assert out[0].symbol is None


def test_doc_paragrafo_gigante_quebra_linha_a_linha():
    """Parágrafo único > cap → pré-quebra linha a linha (linha 290)."""
    # um parágrafo (sem \n\n) gigante
    src = "## A\n\n" + "\n".join(f"linha {i} " + "x" * 50 for i in range(200))
    out = chunker.chunk_doc("d.md", src)
    assert len(out) > 1
    assert all(c.approx_tokens <= chunker.DOC_MAX_TOK + 5 for c in out)


def test_config_toml_preamble_sem_section():
    """TOML com pares soltos antes de [section] → preamble (linha 358)."""
    src = 'titulo = "x"\n\n[secao]\nchave = 1\n'
    out = chunker.chunk_config("c.toml", "toml", src)
    assert out
    assert any("titulo" in c.content for c in out)


def test_config_yaml_documento_multiplo():
    """S83: YAML multi-documento (---) SEPARA os documentos (fix do bug S82).

    Antes (S82): o `---` separava em `items`, mas o merge (CFG_MIN_TOK) juntava
    de volta. Agora a fronteira de documento BLOQUEIA o merge — cada documento
    vira chunk(s) próprio(s), mesmo minúsculo.
    """
    src = "a: 1\n---\nb: 2\n---\nc: 3\n"
    out = chunker.chunk_config("c.yml", "yaml", src)
    assert len(out) == 3  # 3 documentos separados
    assert "a: 1" in out[0].content
    assert "b: 2" in out[1].content
    assert "c: 3" in out[2].content


def test_config_yaml_documento_multiplo_grande_separa():
    """S83: documentos YAML grandes também ficam separados."""
    doc = "\n".join(f"k{i}: {i}" for i in range(50))
    src = f"{doc}\n---\n{doc}\n"
    out = chunker.chunk_config("c.yml", "yaml", src)
    assert len(out) >= 2  # documentos NÃO fundem
    assert out[0].content.count("k0:") == 1  # cada doc no seu chunk


def test_config_yaml_sem_separador_ainda_funde():
    """S83: sem `---`, o merge normal continua (chaves minúsculas fundem)."""
    src = "a: 1\nb: 2\nc: 3\n"
    out = chunker.chunk_config("c.yml", "yaml", src)
    assert len(out) == 1  # sem fronteira → funde (comportamento normal)


def test_config_bloco_unico_gigante_quebra():
    """Bloco único > CFG_MAX_TOK → janela (linha 418-419)."""
    src = "chave: |\n" + "\n".join(f"  linha {i}" for i in range(400))
    out = chunker.chunk_config("c.yml", "yaml", src)
    assert out
    assert all(c.approx_tokens <= chunker.CFG_MAX_TOK + 5 for c in out)


def test_chunk_file_kind_desconhecido_levanta():
    """kind inválido → ValueError (linha 437)."""
    import pytest
    with pytest.raises(ValueError, match="kind desconhecido"):
        chunker.chunk_file("x.bin", "binary", None, "data")
