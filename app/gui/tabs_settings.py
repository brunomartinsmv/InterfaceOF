from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.dir_prefix = QLineEdit('case_')
        self.log_prefix = QLineEdit('log_')

        self.plot_time_stride = QDoubleSpinBox()
        self.plot_time_stride.setDecimals(6)
        self.plot_time_stride.setRange(0.0, 1_000_000.0)
        self.plot_time_stride.setSingleStep(0.01)
        self.plot_time_stride.setValue(0.0)
        self.plot_time_stride.setToolTip('0 desativa o espaçamento por tempo. Quando > 0, o gráfico usa tempo no eixo x e amostra um ponto a cada Δt mínimo.')

        self.plot_iteration_stride = QSpinBox()
        self.plot_iteration_stride.setRange(1, 1_000_000)
        self.plot_iteration_stride.setValue(1)
        self.plot_iteration_stride.setToolTip('Usado quando o espaçamento por tempo estiver desativado ou não houver tempo disponível no log. 1 = plota todos os pontos aceitos.')

        self.setup_commands = QPlainTextEdit('blockMesh')
        self.stage_commands = QPlainTextEdit('foamRun')
        self.post_commands = QPlainTextEdit('')
        self.setup_commands.setPlaceholderText('Um comando por linha')
        self.stage_commands.setPlaceholderText('Um comando por linha')
        self.post_commands.setPlaceholderText('Um comando por linha')

        form = QFormLayout()
        form.addRow('Prefixo diretório', self.dir_prefix)
        form.addRow('Prefixo log', self.log_prefix)
        form.addRow('Δtempo mínimo entre pontos (s)', self.plot_time_stride)
        form.addRow('Plotar a cada N pontos/iterações', self.plot_iteration_stride)

        commands_box = QGroupBox('Comandos do modo interno')
        commands_form = QFormLayout(commands_box)
        commands_form.addRow('Setup commands', self.setup_commands)
        commands_form.addRow('Stage/run commands', self.stage_commands)
        commands_form.addRow('Post commands', self.post_commands)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(commands_box)
        layout.addStretch(1)
