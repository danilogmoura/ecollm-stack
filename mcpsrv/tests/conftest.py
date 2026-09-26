import sys
from pathlib import Path

# mcpsrv/tests/conftest.py -> garante a raiz do repo no sys.path (pacotes `mcpsrv`, `ingest`).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
