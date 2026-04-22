from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ALLOWED_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(slots=True)
class NormalizationResult:
    original: str
    normalized: str


def strip_accents(text: str) -> str:
    return ''.join(
        ch for ch in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(ch)
    )


def normalize_token(value: object) -> str:
    text = '' if value is None else str(value)
    text = strip_accents(text.strip().lower())
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text


def ensure_valid_token(value: object) -> str:
    token = normalize_token(value)
    if not token:
        raise ValueError('Token vazio após normalização.')
    if not _ALLOWED_RE.fullmatch(token):
        raise ValueError(f'Token inválido após normalização: {token}')
    return token


def is_reserved_config_column(name: str) -> bool:
    return name.startswith('cfg__')
