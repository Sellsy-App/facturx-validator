"""Garantit que le package racine est importable pendant les tests,
même sans installation editable (ex. si saxonche n'a pas de wheel)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
