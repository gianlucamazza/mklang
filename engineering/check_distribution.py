"""Verify the pinned distribution without importing it first."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
pin = json.loads((root / "upstream.json").read_text())
for name, expected in pin["sha256"].items():
    actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"engineering distribution drift: {name}")
print("engineering distribution hashes match")
