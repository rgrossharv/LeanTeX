from __future__ import annotations

from pathlib import Path


def write_text_if_changed(path: Path, content: str, encoding: str = "utf-8") -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = path.read_text(encoding=encoding)
            if existing == content:
                return False
        except Exception:
            # If reading fails, fall back to writing fresh content.
            pass
    path.write_text(content, encoding=encoding)
    return True

