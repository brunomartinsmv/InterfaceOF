from __future__ import annotations

from app.core.log_parser import LogParser


def test_log_parser_time():
    parser = LogParser()
    event = parser.parse_line("Time = 0.5")
    assert event.current_time == 0.5
    assert event.error_detected is False

    event2 = parser.parse_line("Time = 1.25e-02")
    assert event2.current_time == 0.0125


def test_log_parser_error_detection():
    parser = LogParser()

    ev1 = parser.parse_line("FOAM FATAL ERROR: keyword solver is undefined")
    assert ev1.error_detected is True
    assert "FOAM FATAL ERROR" in (ev1.error_message or "")

    ev2 = parser.parse_line("Floating point exception (core dumped)")
    assert ev2.error_detected is True

    ev3 = parser.parse_line("bash: foamRun: command not found")
    assert ev3.error_detected is True
