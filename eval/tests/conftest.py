import sys
from pathlib import Path

import pytest

# eval/tests/conftest.py -> raiz do repo (pacotes `eval` e `ingest` importaveis)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_profile_env(monkeypatch):
    """S63: neutraliza o .env REAL nos testes do eval.

    recall.main() agora chama embed.load_dotenv() (fix do footgun do gate), que
    injeta RAG_PROFILE (e demais variaveis) do .env da maquina do dev no os.environ
    do processo. Sem este scrub, um teste que roda main() contamina os seguintes
    (ex.: o perfil resolvido passaria a ser qwen37 em vez do default). Cada teste
    comeca com o env de perfil LIMPO; quem quiser um perfil usa monkeypatch.setenv.
    Espelha o _isolate_profile_env do ingest/tests/conftest.py.
    """
    for var in ("RAG_PROFILE", "RAG_EMBED_MODEL", "RAG_EMBED_DIM"):
        monkeypatch.delenv(var, raising=False)
