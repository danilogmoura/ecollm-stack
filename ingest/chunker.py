"""Chunker da FASE 1 — tres estrategias, travadas no plano §1:

  code   : tree-sitter; 1 chunk por funcao/metodo/classe-top-level (com docstring),
           cap 512 tokens (~4 chars/tok); arquivo sem nodos reconheciveis ou
           bloco acima do cap vira janela deslizante de 400 tok SEM overlap.
  doc    : split por heading `##` (fallback `#`); secoes < 100 tok fazem merge
           com a vizinha; > 512 tok sao divididas com overlap ~12%.
  config : yaml/json por chave top-level; toml por [[section]]/chave top-level;
           alvo 100–300 tok, chunks minusculos adjacentes sao agrupados.

Token = aproximacao len(text)/4 (tiktoken nao e necessario: os limites sao
de granularidade, nao de janela de contexto exata).

O task-prefix NAO e aplicado aqui — chunk guarda texto PURO; prefixo entra em
embed.py (decisao content_hash-vs-prefix do plano).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tree_sitter import Language, Parser

import tree_sitter_python as tsp
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_go as tsgo
import tree_sitter_bash as tsbash

# ---------------------------------------------------------------------------
# tipos comuns
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4
CODE_CAP_TOK = 512
CODE_MIN_TOK = 25          # limiar de MERGE: funcoes minusculas grudam na anterior
CODE_PACK_TOK = 400        # alvo ao empacotar definicoes pequenas vizinhas
CODE_WINDOW_TOK = 400       # chunk orfaos / janelas deslizantes
DOC_MIN_TOK = 100
DOC_MAX_TOK = 512
DOC_OVERLAP = 0.12
CFG_MIN_TOK = 25          # limiar de MERGE: chaves minusculas grudam na anterior
CFG_PACK_TOK = 300        # alvo de empacotamento por chunk (plano: 100-300 tok)
CFG_MAX_TOK = 512         # teto duro: chave unica gigante passa disso e e entao
                          # dividida em janelas de CFG_PACK_TOK


@dataclass(frozen=True)
class Chunk:
    """Unidade indexavel. kind/lang batem com a tabela chunks."""
    path: str
    kind: str            # code | doc | config
    lang: str | None
    symbol: str | None   # nome da funcao/secao/chave (NULL ok)
    content: str         # texto PURO (sem task-prefix)

    @property
    def approx_tokens(self) -> int:
        return len(self.content) // CHARS_PER_TOKEN


def _est_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# código — tree-sitter
# ---------------------------------------------------------------------------

_LANGS: dict[str, Language] = {
    "python": Language(tsp.language()),
    "javascript": Language(tsjs.language()),
    "typescript": Language(tsts.language_typescript()),
    "tsx": Language(tsts.language_tsx()),
    "go": Language(tsgo.language()),
    "bash": Language(tsbash.language()),
}
_PARSERS = {k: Parser(v) for k, v in _LANGS.items()}

# nomes de nodo que viram chunk-unit na ARVORE RAIZ (top-level apenas):
# funcoes/metodos/classes de qualquer profundidade geram chunk proprio quando
# aninhados? NAO — plano diz 1-funcao; para evitar chunk duplicado (classe +
# seus metodos), emitimos o MAIOR contenedor top-level e descrevemos dentro.
_TOP_NODES = {
    "function_definition", "method_definition", "class_definition",
    "function_declaration", "method_definition", "generator_function_declaration",
    "abstract_class_declaration", "module", "type_alias_declaration",
    "interface_declaration", "enum_declaration",
    "function_declaration", "method_declaration", "type_declaration",
    "const_declaration",  # go: agrupa; tratado com filtro de nome abaixo
    "declaration_list",   # bash: functions aparecem aqui
}

_NAME_RE = re.compile(rb"")  # placeholder p/ futura extensao


def _node_name(node, src: bytes) -> str | None:
    """Melhor esforco para extrair o nome simbolico de um nodo de definicao."""
    for field in ("name", "path"):
        child = node.child_by_field_name(field)
        if child is not None:
            return src[child.start_byte:child.end_byte].decode("utf-8", "replace")
    # padrao: primeiro filho identifier/type_identifier/string
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier",
                          "statement", "word"):
            return src[child.start_byte:child.end_byte].decode("utf-8", "replace")
    return None


def _split_lines_window(text: str, window_tok: int) -> list[str]:
    """Janela por linhas; NAO corta expressao no meio quando a linha couber.
    Linha unica maior que o limite e dividida dura em blocos de `limit` chars
    (sem isso, paragrafo de uma linha sozinha passava inteiro — ver BUG-003)."""
    limit = window_tok * CHARS_PER_TOKEN
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for ln in text.splitlines(keepends=True):
        while len(ln) > limit:          # linha gigante: corte duro por chars
            room = limit - size
            if room > 0:
                buf.append(ln[:room])
                ln = ln[room:]
                size = limit
            out.append("".join(buf))
            buf, size = [], 0
        if size + len(ln) > limit and buf:
            out.append("".join(buf))
            buf, size = [], 0
        buf.append(ln)
        size += len(ln)
    if buf:
        out.append("".join(buf))
    return out


def chunk_code(path: str, lang: str | None, source: str) -> list[Chunk]:
    if lang not in _PARSERS or not source.strip():
        # sem gramatica (ou arquivo vazio) → janela orfa de 400 tok
        return [Chunk(path, "code", lang, None, w)
                for w in _split_lines_window(source, CODE_WINDOW_TOK)] if source.strip() else []

    parser = _PARSERS[lang]
    src_bytes = source.encode("utf-8")
    tree = parser.parse(src_bytes)

    chunks: list[Chunk] = []
    leftovers: list[tuple[int, int]] = []  # regioes (bytes) ja cobertas

    def emit(node, name):
        text = src_bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")
        toks = _est_tokens(text)
        if toks <= CODE_CAP_TOK:
            chunks.append(Chunk(path, "code", lang, name, text))
        else:
            # funcao gigante: janela deslizante DENTRO dela, mantendo contexto
            parts = _split_lines_window(text, CODE_WINDOW_TOK)
            for i, part in enumerate(parts):
                chunks.append(Chunk(path, "code", lang,
                                    f"{name}#{i+1}" if name else None, part))

    for node in tree.root_node.children:
        if node.type in _TOP_NODES or node.type.endswith("_definition") or node.type.endswith("_declaration"):
            name = _node_name(node, src_bytes)
            # go const_declaration sem identificador util: trata como leftover
            if node.type == "const_declaration" and name is None:
                continue
            emit(node, name)
            leftovers.append((node.start_byte, node.end_byte))

    # ---- leftover: linhas fora das definicoes (imports, constantes, scripts
    # bash soltos, blocos IF_TOPLEVEL etc.) → janelas de 400 tok sem overlap
    covered = bytearray(len(src_bytes))
    for s, e in leftovers:
        covered[s:e] = b"\x01" * (e - s)
    rest_spans: list[tuple[int, int]] = []
    i = 0
    n = len(src_bytes)
    while i < n:
        if covered[i] == 0:
            j = i
            while j < n and covered[j] == 0:
                j += 1
            span_text = src_bytes[i:j].decode("utf-8", "replace").strip()
            if span_text:
                rest_spans.append((i, j))
            i = j
        else:
            i += 1
    for s, e in rest_spans:
        text = src_bytes[s:e].decode("utf-8", "replace").strip("\n")
        if _est_tokens(text) <= CODE_WINDOW_TOK:
            chunks.append(Chunk(path, "code", lang, None, text))
        else:
            for i2, part in enumerate(_split_lines_window(text, CODE_WINDOW_TOK)):
                chunks.append(Chunk(path, "code", lang, None, part))

    # fusao de chunks minusculos (< CODE_MIN_TOK) no anterior enquanto o resultado
    # couber no alvo de empacotamento (CODE_PACK_TOK), nunca acima do cap 512
    merged: list[Chunk] = []
    for c in chunks:
        if (merged and c.approx_tokens < CODE_MIN_TOK
                and merged[-1].approx_tokens + c.approx_tokens <= CODE_PACK_TOK):
            prev = merged[-1]
            merged[-1] = Chunk(prev.path, prev.kind, prev.lang, prev.symbol,
                               prev.content + "\n" + c.content)
        elif merged and merged[-1].approx_tokens < CODE_MIN_TOK:
            prev = merged[-1]  # anterior estava minusculo: absorve este
            merged[-1] = Chunk(prev.path, prev.kind, prev.lang, prev.symbol,
                               prev.content + "\n" + c.content)
        else:
            merged.append(c)
    return merged


# ---------------------------------------------------------------------------
# docs — markdown por headings
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_doc(path: str, source: str) -> list[Chunk]:
    if not source.strip():
        return []
    # nivel do "heading de secao": ## se existir, senao #
    levels = [len(m.group(1)) for m in
              (_HEADING_RE.match(l) for l in source.splitlines()) if m]
    sec_level = 2 if any(lvl == 2 for lvl in levels) else (min(levels) if levels else 1)

    # divide em blocos: preamble + um por heading do nivel escolhido
    blocks: list[tuple[str | None, str]] = []  # (titulo, corpo)
    cur_title: str | None = None
    cur_lines: list[str] = []
    fence = False
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            fence = not fence
        m = None if fence else _HEADING_RE.match(line.rstrip("\n"))
        if m and len(m.group(1)) == sec_level:
            if cur_lines or cur_title is not None:
                blocks.append((cur_title, "".join(cur_lines)))
            cur_title = m.group(2).strip()
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_lines or cur_title is not None:
        blocks.append((cur_title, "".join(cur_lines)))

    # preambulo minusculo (< DOC_MIN_TOK) e absorvido pela primeira secao com
    # titulo, que passa a batizar o chunk (BUG-003). Secoes com titulo so se
    # fundem na anterior quando a anterior ja e uma secao "cheia" (>=
    # DOC_MIN_TOK): assim um heading de transicao minisculo nao vira chunk
    # orfao, mas duas secoes pequenas distintas continuam separadas, como
    # manda a divisao por "##" do plano §3 (test_doc_divide_por_h2).
    merged: list[tuple[str | None, str]] = []
    for title, body in blocks:
        prev_is_full = bool(merged) and (
            merged[-1][0] is None or _est_tokens(merged[-1][1]) >= DOC_MIN_TOK)
        if (merged and prev_is_full and _est_tokens(body) < DOC_MIN_TOK
                and _est_tokens(merged[-1][1]) + _est_tokens(body) <= DOC_MAX_TOK):
            pt, pb = merged[-1]
            merged[-1] = (pt or title,
                          pb + ("\n" + body if not body.startswith("\n") else body))
        else:
            merged.append((title, body))

    # split de secoes grandes com overlap ~12% por paragrafo
    out: list[Chunk] = []
    for title, body in merged:
        if _est_tokens(body) <= DOC_MAX_TOK:
            parts = [body]
        else:
            max_chars = DOC_MAX_TOK * CHARS_PER_TOKEN
            # 1) pre-quebra paragrafos gigantes linha a linha em janela menor
            #    que o cap, deixando margem para a acumulacao abaixo inserir a
            #    cauda comum (~12%) sem estourar DOC_MAX_TOK. O overlap entre
            #    partes vem SO da acumulacao (passo 2); se o pre-break tambem
            #    duplicasse linhas, as partes ficariam com ate ~24% de
            #    repeticao e o cap seria estourado (BUG-004).
            break_tok = int(DOC_MAX_TOK * (1 - DOC_OVERLAP))
            atoms: list[str] = []
            for p in re.split(r"\n\s*\n", body):
                if not p.strip():
                    continue
                if len(p) <= max_chars:
                    atoms.append(p)
                else:
                    atoms.extend(_split_lines_window(p, break_tok))
            # 2) acumula atomos ate o cap; novo bloco comeca com cauda (~12%)
            parts: list[str] = []
            buf: list[str] = []
            size = 0
            for a in atoms:
                add = len(a) + 2
                if size + add > max_chars and buf:
                    parts.append("\n\n".join(buf))
                    # cauda de ~12% para o proximo bloco. Se nenhum atomo
                    # inteiro couber no orcamento (atomos do pre-break sao
                    # maiores que 12% do cap), corta linha a linha o fim do
                    # ultimo atomo — senao o overlap seria zero (BUG-005).
                    tail: list[str] = []
                    tsize = 0
                    for q in reversed(buf):
                        if tsize + len(q) <= DOC_OVERLAP * max_chars:
                            tail.insert(0, q)
                            tsize += len(q)
                            continue
                        if not tail:
                            for r in reversed(q.splitlines()):
                                if tsize + len(r) + 1 > DOC_OVERLAP * max_chars:
                                    break
                                tail.insert(0, r)
                                tsize += len(r) + 1
                        break
                    buf, size = tail, tsize
                buf.append(a)
                size += add
            if buf:
                parts.append("\n\n".join(buf))
        for i, part in enumerate(parts):
            sym = f"{title} ({i+1})" if title and len(parts) > 1 else title
            out.append(Chunk(path, "doc", "markdown", sym,
                             _anchor_doc(path, sym, part)))
    return out


def _anchor_doc(path: str, heading: str | None, body: str) -> str:
    """S19 (T-RET-1): âncora `path > heading` no TOPO do conteúdo de chunks doc.

    O chunk perde o contexto de ONDE vive quando é embedado isolado; prefixar a
    linha `path > heading` dá ao vetor e ao tsvector a âncora da seção, ajudando
    perguntas que citam o arquivo/título (ex.: q03 'Gotchas'). A âncora entra no
    `content` armazenado (e portanto no embed e no content_hash), mas NUNCA na
    string de heading duplicada — só uma linha à frente. Se já começar com a
    mesma âncora (re-processamento), não repete.
    """
    if not heading:
        return body
    anchor = f"{path} > {heading}"
    first_line = body.lstrip().split("\n", 1)[0].strip() if body.strip() else ""
    if first_line == anchor:
        return body
    return f"{anchor}\n{body}"


# ---------------------------------------------------------------------------
# config — yaml/json por chave top-level, toml por section
# ---------------------------------------------------------------------------

def chunk_config(path: str, lang: str | None, source: str) -> list[Chunk]:
    if not source.strip():
        return []
    items: list[tuple[str | None, str]] = []  # (chave, bloco textual)

    if lang == "toml":
        # [[table]] / [table] / pares soltos no preamble
        cur_key: str | None = "__preamble__"
        buf: list[str] = []
        for line in source.splitlines(keepends=True):
            if re.match(r"^\s*\[\[?[A-Za-z0-9_.\"-]+\]?\]?\s*$", line):
                if buf:
                    items.append((cur_key, "".join(buf)))
                cur_key = line.strip().strip("[]")
                buf = [line]
            else:
                buf.append(line)
        if buf:
            items.append((cur_key, "".join(buf)))
    elif lang in ("yaml", "json"):
        # corte estrutural por indentacao zero (chaves/documentos de topo),
        # preservando o texto original do bloco (comentarios inclusos)
        lines = source.splitlines(keepends=True)
        cur_key = None
        buf = []
        for line in lines:
            if lang == "yaml" and re.match(r"^---\s*$", line):
                if buf:
                    items.append((cur_key or "document", "".join(buf)))
                    buf, cur_key = [], None
                continue
            if re.match(r"^[^#\s\-]", line) and ":" in line.split("#")[0]:
                if buf:
                    items.append((cur_key or "block", "".join(buf)))
                    buf = []
                cur_key = line.split(":", 1)[0].strip()
            buf.append(line)
        if buf:
            items.append((cur_key or "block", "".join(buf)))
    else:
        return [Chunk(path, "config", lang, None, w)
                for w in _split_lines_window(source, CFG_MAX_TOK)]

    # empacota: itens < CFG_MIN_TOK grudam no anterior; chunk fecha ao passar de
    # CFG_PACK_TOK (alvo do plano) ou se o proximo item estourar o teto duro
    grouped: list[tuple[str | None, str]] = []
    for key, body in items:
        if (grouped and _est_tokens(body) < CFG_MIN_TOK
                and _est_tokens(grouped[-1][1]) + _est_tokens(body) <= CFG_PACK_TOK):
            pk, pb = grouped[-1]
            grouped[-1] = (pk, pb + body)
        elif (grouped and _est_tokens(grouped[-1][1]) < CFG_MIN_TOK
                and _est_tokens(grouped[-1][1]) + _est_tokens(body) <= CFG_PACK_TOK):
            pk, pb = grouped[-1]  # anterior era minusculo: absorve o atual
            grouped[-1] = (pk, pb + body)
        else:
            grouped.append((key, body))

    # bloco unico maior que o teto: janela final (arquivo degenerado/minificado)
    out: list[Chunk] = []
    for key, body in grouped:
        if _est_tokens(body) > CFG_MAX_TOK:
            for i, part in enumerate(_split_lines_window(body, CFG_PACK_TOK)):
                out.append(Chunk(path, "config", lang,
                                 f"{key}#{i+1}" if key else None, part))
        else:
            out.append(Chunk(path, "config", lang, key, body))
    return out


# ---------------------------------------------------------------------------
# fachada usada pelo cli/ingest
# ---------------------------------------------------------------------------

def chunk_file(path: str, kind: str, lang: str | None, source: str) -> list[Chunk]:
    if kind == "code":
        return chunk_code(path, lang, source)
    if kind == "doc":
        return chunk_doc(path, source)
    if kind == "config":
        return chunk_config(path, lang, source)
    raise ValueError(f"kind desconhecido: {kind}")
