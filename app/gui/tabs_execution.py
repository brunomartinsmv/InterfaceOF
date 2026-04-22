from __future__ import annotations

from collections import deque

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
        self._flush_timer.setInterval(250 if active else 1000)
        if active:
            self._flush_console()

    def append_console(self, text: str) -> None:
        self._pending_console_lines.append(text)
        if len(self._pending_console_lines) > 2000:
            while len(self._pending_console_lines) > 1200:
                self._pending_console_lines.popleft()
        if self._active and len(self._pending_console_lines) >= 50:
            self._flush_console()

    def _flush_console(self) -> None:
        if not self._pending_console_lines:
            return
        batch: list[str] = []
        limit = 250 if self._active else 80
        while self._pending_console_lines and len(batch) < limit:
            batch.append(self._pending_console_lines.popleft())
        self.console.moveCursor(QTextCursor.End)
        self.console.insertPlainText(''.join(batch))
        self.console.moveCursor(QTextCursor.End)

    def clear_console(self) -> None:
        self._pending_console_lines.clear()
        self.console.clear()

    def populate_queue(self, cases) -> None:
        self.case_outputs = {}
        self.open_all_button.setEnabled(False)
        self.queue_table.setRowCount(len(cases))
        self.queue_table.setUpdatesEnabled(False)
        try:
            for row_idx, case in enumerate(cases):
                values = [case.case_name, 'queued', case.config_parameters.get('cfg__solver', ''), str(len(case.stages))]
                for col_idx, value in enumerate(values):
                    item = self.queue_table.item(row_idx, col_idx)
                    if item is None:
                        self.queue_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
                    else:
                        item.setText(str(value))
                button = QPushButton('Abrir')
                button.setEnabled(False)
                button.clicked.connect(lambda _=False, name=case.case_name: self.open_case_requested.emit(name))
                self.queue_table.setCellWidget(row_idx, 4, button)
        finally:
            self.queue_table.setUpdatesEnabled(True)
            self.queue_table.viewport().update()

    def reset_statuses(self) -> None:
        self.queue_table.setUpdatesEnabled(False)
        try:
            for row_idx in range(self.queue_table.rowCount()):
                item = self.queue_table.item(row_idx, self.STATUS_COLUMN)
                if item is None:
                    self.queue_table.setItem(row_idx, self.STATUS_COLUMN, QTableWidgetItem('queued'))
                else:
                    item.setText('queued')
        finally:
            self.queue_table.setUpdatesEnabled(True)
            self.queue_table.viewport().update()

    def update_case_status(self, case_name: str, status: str) -> None:
        self.queue_table.setUpdatesEnabled(False)
        try:
            for row_idx in range(self.queue_table.rowCount()):
                item = self.queue_table.item(row_idx, 0)
                if item and item.text() == case_name:
                    status_item = self.queue_table.item(row_idx, self.STATUS_COLUMN)
                    if status_item is None:
                        self.queue_table.setItem(row_idx, self.STATUS_COLUMN, QTableWidgetItem(status))
                    else:
                        status_item.setText(status)
                    break
        finally:
            self.queue_table.setUpdatesEnabled(True)
            self.queue_table.viewport().update()

    def set_case_output(self, case_name: str, case_dir: str, foam_file: str) -> None:
        self.case_outputs[case_name] = {'case_dir': case_dir, 'foam_file': foam_file}
        self.open_all_button.setEnabled(bool(self.case_outputs))
        for row_idx in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row_idx, 0)
            if item and item.text() == case_name:
                button = self.queue_table.cellWidget(row_idx, 4)
                if button is not None:
                    button.setEnabled(True)
                break

    def apply_case_outputs_from_statuses(self, statuses) -> None:
        for status in statuses:
            case_dir = status.metrics.get('case_dir')
            foam_file = status.metrics.get('foam_file')
            if case_dir and foam_file:
                self.set_case_output(status.case_name, str(case_dir), str(foam_file))

    def _emit_open_all(self) -> None:
        if self.case_outputs:
            self.open_all_requested.emit()
