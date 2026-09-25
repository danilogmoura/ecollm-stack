import sys
from pathlib import Path

# eval/tests/conftest.py -> raiz do repo (pacotes `eval` e `ingest` importaveis)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
