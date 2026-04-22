from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_case_directory(src: Path, dst: Path) -> None:
    if dst.exists():
        raise FileExistsError(f'Diretório de destino já existe: {dst}')
    shutil.copytree(src, dst)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding='utf-8')


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
