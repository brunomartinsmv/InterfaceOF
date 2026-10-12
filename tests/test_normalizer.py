from __future__ import annotations

import pytest
from app.utils.normalizer import (
    ensure_valid_token,
    is_reserved_config_column,
    normalize_token,
    strip_accents,
)


def test_strip_accents():
    assert strip_accents("Ângulo") == "Angulo"
    assert strip_accents("viscosidade_cinemática") == "viscosidade_cinematica"
    assert strip_accents("ação") == "acao"


def test_normalize_token():
    assert normalize_token("Ângulo Contato") == "angulo_contato"
    assert normalize_token("  Pressao--Inicial__  ") == "pressao_inicial"
    assert normalize_token("Delta_T_1") == "delta_t_1"
    assert normalize_token("cfg__solver") == "cfg_solver"  # normalize_token condensa '__' para '_'
    assert normalize_token("") == ""
    assert normalize_token(None) == ""


def test_ensure_valid_token():
    assert ensure_valid_token("Viscosidade") == "viscosidade"
    assert ensure_valid_token("vel_x") == "vel_x"

    with pytest.raises(ValueError, match="Token vazio"):
        ensure_valid_token("   ")

    with pytest.raises(ValueError, match="Token vazio"):
        ensure_valid_token("---")


def test_is_reserved_config_column():
    assert is_reserved_config_column("cfg__solver") is True
    assert is_reserved_config_column("cfg__n_processors") is True
    assert is_reserved_config_column("viscosidade") is False
    assert is_reserved_config_column("cfg_solver") is False
