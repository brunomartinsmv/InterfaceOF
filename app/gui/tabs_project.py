from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ProjectTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.base_case_edit = QLineEdit()
        self.primary_csv_edit = QLineEdit()
        self.secondary_csv_edit = QLineEdit()
        self.output_dir_edit = QLineEdit()
        self.audit_table = QTableWidget(0, 5)
        self.audit_table.setHorizontalHeaderLabels(['variavel', 'arquivo', 'linha', 'status', 'origem'])
        self.validation_label = QLabel('Projeto ainda não validado.')
        self.validate_button = QPushButton('Validar projeto')

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow('Pasta base', self._with_browse(self.base_case_edit, True))
        form.addRow('CSV primário', self._with_browse(self.primary_csv_edit, False))
        form.addRow('CSV secundário', self._with_browse(self.secondary_csv_edit, False, optional=True))
        form.addRow('Pasta de output', self._with_browse(self.output_dir_edit, True))
        layout.addLayout(form)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.validation_label)
        layout.addWidget(self.audit_table)

    def _with_browse(self, edit: QLineEdit, directory: bool, optional: bool = False) -> QWidget:
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        button = QPushButton('...')
        row.addWidget(button)

        def _browse() -> None:
            if directory:
                path = QFileDialog.getExistingDirectory(self, 'Selecionar diretório')
            else:
                path, _ = QFileDialog.getOpenFileName(self, 'Selecionar arquivo', filter='CSV (*.csv);;Todos (*.*)')
            if path:
                edit.setText(path)
            elif optional:
                edit.setText('')

        button.clicked.connect(_browse)
        return wrapper

    def populate_audit_table(self, rows) -> None:
        self.audit_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [row.variable, row.file_path, str(row.line_number), row.status, row.origin]
            for col_idx, value in enumerate(values):
                self.audit_table.setItem(row_idx, col_idx, QTableWidgetItem(value))
