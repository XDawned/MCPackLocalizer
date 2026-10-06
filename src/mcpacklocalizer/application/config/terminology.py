"""Lazy preset catalog, with bounded page results for desktop browsing."""
from __future__ import annotations

import json
import threading
from itertools import islice
from pathlib import Path

from .settings import validate_glossary


class GlossaryCatalog:
    def __init__(self):
        self.lock = threading.Lock()
        self.signature = None
        self.data = {}

    def query(self, path, overrides, inline, search="", page=0, size=100, custom=False):
        if not 1 <= size <= 200 or page < 0:
            raise ValueError("术语预设分页参数无效")
        with self.lock:
            extra = {}
            if overrides:
                extra.update(validate_glossary(Path(overrides).read_text(encoding="utf-8-sig")))
            extra.update(validate_glossary(inline))
            if custom:
                data = extra
            elif path:
                stat = Path(path).stat()
                signature = (path, stat.st_mtime_ns, stat.st_size)
                if signature != self.signature:
                    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                    if not isinstance(raw, dict):
                        raise ValueError("术语预设必须是 JSON 对象")
                    # Legacy presets contain a few empty display keys; mirror the
                    # engine's tolerance rather than rejecting the entire catalog.
                    self.data = {key: value for key, value in raw.items() if key.strip() and
                                 (isinstance(value, str) or isinstance(value, list) and all(isinstance(v, str) for v in value))}
                    self.signature = signature
                data = self.data
            else:
                data = {}
            needle = search.strip().casefold()
            start = page * size
            if needle:
                rows, total = [], 0
                for source, preset in data.items():
                    effective = extra.get(source, preset)
                    display = effective if isinstance(effective, str) else " / ".join(effective)
                    if needle in source.casefold() or needle in display.casefold():
                        if start <= total < start + size:
                            rows.append((source, display))
                        total += 1
            else:
                total = len(data)
                rows = [(source, value if isinstance(value := extra.get(source, preset), str) else " / ".join(value))
                        for source, preset in islice(data.items(), start, start + size)]
            return {"rows": rows, "total": total, "page": page, "size": size}
