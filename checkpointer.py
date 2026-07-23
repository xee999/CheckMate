"""checkpointer.py — JSON cache for Bod pipeline stages."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

class Checkpointer:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _input_hash(self, rfp_path: str, sub_path: str, config: dict | None = None) -> str:
        """SHA256 of input state (paths, mtime, config)."""
        hasher = hashlib.sha256()
        rfp = Path(rfp_path)
        if rfp.exists():
            hasher.update(str(rfp.resolve()).encode())
            hasher.update(str(rfp.stat().st_mtime).encode())
        sub = Path(sub_path)
        if sub.is_dir():
            for f in sorted(sub.rglob("*")):
                if f.is_file():
                    hasher.update(str(f.resolve()).encode())
                    hasher.update(str(f.stat().st_mtime).encode())
        if config:
            hasher.update(json.dumps(config, sort_keys=True).encode())
        return hasher.hexdigest()[:16]

    @property
    def current_dir(self) -> Path:
        return self.cache_dir

    def stage_path(self, rfp_path: str, sub_path: str, stage: str) -> Path:
        h = self._input_hash(rfp_path, sub_path)
        return self.cache_dir / f"{h}_{stage}.json"

    def save(self, rfp_path: str, sub_path: str, stage: str, data: Any):
        path = self.stage_path(rfp_path, sub_path, stage)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.cache_dir, suffix=".json", delete=False,
        ) as f:
            tmp = Path(f.name)
            json.dump(data, f, indent=2, default=str)
        tmp.replace(path)

    def load(self, rfp_path: str, sub_path: str, stage: str) -> Any | None:
        path = self.stage_path(rfp_path, sub_path, stage)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                path.unlink(missing_ok=True)
                return None
        return None

    def clear(self, rfp_path: str, sub_path: str):
        prefix = self._input_hash(rfp_path, sub_path)
        for f in self.cache_dir.glob(f"{prefix}_*.json"):
            f.unlink()
