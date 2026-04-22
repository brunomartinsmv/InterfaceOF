from __future__ import annotations

from pathlib import Path


def require_existing_dir(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if not path.is_dir():
        raise FileNotFoundError(f'{label} inválido: {path}')
    return path


def require_existing_file(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f'{label} inválido: {path}')
    return path
