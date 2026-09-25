import sys
from pathlib import Path

# ingest/tests/conftest.py -> raiz do repo (ingest/ precisa estar importavel)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
