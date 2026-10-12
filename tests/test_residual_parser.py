from __future__ import annotations

from app.core.residual_parser import ResidualParser


def test_parse_residual_full():
    parser = ResidualParser()
    line = "smoothSolver:  Solving for Ux, Initial residual = 0.054321, Final residual = 0.000123, No Iterations 5"
    point = parser.parse_line(line)
    assert point is not None
    assert point.equation == "Ux"
    assert point.initial_residual == 0.054321
    assert point.final_residual == 0.000123


def test_parse_residual_initial_only():
    parser = ResidualParser()
    line = "GAMG:  Solving for p_rgh, Initial residual = 0.0025, No Iterations 2"
    point = parser.parse_line(line)
    assert point is not None
    assert point.equation == "p_rgh"
    assert point.initial_residual == 0.0025
    assert point.final_residual is None


def test_parse_residual_scientific_notation():
    parser = ResidualParser()
    line = "PBiCGStab:  Solving for T.air, Initial residual = 1.25e-05, Final residual = 3.4e-07, No Iterations 1"
    point = parser.parse_line(line)
    assert point is not None
    assert point.equation == "T.air"
    assert point.initial_residual == 1.25e-05
    assert point.final_residual == 3.4e-07


def test_parse_residual_unrelated_line():
    parser = ResidualParser()
    assert parser.parse_line("Time = 0.05") is None
    assert parser.parse_line("Courant Number mean: 0.1 max: 0.45") is None
