from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ExecutionTab(QWidget):
    open_case_requested = Signal(str)
    open_all_requested = Signal()
    open_paraview_requested = open_case_requested
    open_all_paraview_requested = open_all_requested

    STATUS_COLUMN = 1

    def __init__(self) -> None:
        super().__init__()
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(['case_name', 'status', 'solver', 'n_stages', 'ParaView'])
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2500)
        self.run_button = QPushButton('Iniciar campanha')
        self.stop_button = QPushButton('Parar caso atual')
        self.open_all_button = QPushButton('Abrir todos em um ParaView')
        self.open_all_button.setEnabled(False)

        self.case_outputs: dict[str, dict[str, str]] = {}
        self._pending_console_lines: deque[str] = deque()
        self._active = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(250)
        self._flush_timer.timeout.connect(self._flush_console)
        self._flush_timer.start()

        layout = QVBoxLayout(self)
        buttons = QHBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.open_all_button)
        layout.addWidget(self.queue_table)
        layout.addLayout(buttons)
        layout.addWidget(self.console)

        self.open_all_button.clicked.connect(self._emit_open_all)

    def set_active(self, active: bool) -> None:
        self._active = active

    def clear_console(self) -> None:
        self.console.clear()
        self._pending_console_lines.clear()

    def append_console(self, text: str) -> None:
        self._pending_console_lines.append(text)

    def _flush_console(self) -> None:
        if not self._pending_console_lines:
            return
        chunk = ''.join(self._pending_console_lines)
        self._pending_console_lines.clear()
        self.console.moveCursor(QTextCursor.End)
        self.console.insertPlainText(chunk)
        self.console.moveCursor(QTextCursor.End)

    def populate_queue(self, cases: list) -> None:
        self.case_outputs.clear()
        self.open_all_button.setEnabled(False)
        self.queue_table.setRowCount(len(cases))
        for row, case in enumerate(cases):
            self.queue_table.setItem(row, 0, QTableWidgetItem(case.case_name))
            self.queue_table.setItem(row, 1, QTableWidgetItem('queued'))
            solver = case.config_parameters.get('cfg__solver', '-')
            self.queue_table.setItem(row, 2, QTableWidgetItem(solver))
            self.queue_table.setItem(row, 3, QTableWidgetItem(str(len(case.stages))))
            btn = QPushButton('ParaView')
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, name=case.case_name: self.open_case_requested.emit(name))
            self.queue_table.setCellWidget(row, 4, btn)

    def update_case_status(self, case_name: str, status: str) -> None:
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if item and item.text() == case_name:
                self.queue_table.setItem(row, self.STATUS_COLUMN, QTableWidgetItem(status))
                break

    def reset_statuses(self) -> None:
        self.case_outputs.clear()
        for row in range(self.queue_table.rowCount()):
            self.queue_table.setItem(row, self.STATUS_COLUMN, QTableWidgetItem('queued'))
            widget = self.queue_table.cellWidget(row, 4)
            if widget:
                widget.setEnabled(False)
        self.open_all_button.setEnabled(False)

    def apply_case_outputs_from_statuses(self, statuses: list) -> None:
        self.case_outputs.clear()
        for st in statuses:
            self.case_outputs[st.case_name] = {
                'case_dir': st.metrics.get('case_dir', ''),
                'foam_file': st.metrics.get('foam_file', ''),
            }
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if not item:
                continue
            case_name = item.text()
            payload = self.case_outputs.get(case_name)
            widget = self.queue_table.cellWidget(row, 4)
            if widget and payload and payload.get('foam_file') and Path(payload['foam_file']).is_file():
                widget.setEnabled(True)
        has_any_available = any(Path(p.get('foam_file', '')).is_file() for p in self.case_outputs.values())
        self.open_all_button.setEnabled(has_any_available)

    def _emit_open_all(self) -> None:
        self.open_all_requested.emit()
