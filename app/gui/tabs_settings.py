from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.environment_adapter import EnvironmentAdapter


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._environment = EnvironmentAdapter()

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

        host = self._environment.host_kind()
        bash = self._environment.resolve_bash()
        self.host_label = QLabel(f'Host: {host} | bash: {bash}')

        self.activation_enabled = QCheckBox('Carregar ambiente OpenFOAM antes de cada comando')
        self.activation_command = QLineEdit()
        self.activation_command.setPlaceholderText('source ~/OpenFOAM/OpenFOAM-13/etc/bashrc')
        suggested = self._environment.suggested_activation_command()
        if suggested:
            self.activation_command.setText(suggested)
        if not self._environment.openfoam_on_path() and suggested:
            self.activation_enabled.setChecked(True)

        self.probe_button = QPushButton('Verificar ambiente')
        self.probe_label = QLabel(self._initial_probe_hint())
        self.probe_label.setWordWrap(True)

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

        env_box = QGroupBox('Ambiente OpenFOAM')
        env_layout = QVBoxLayout(env_box)
        env_layout.addWidget(self.host_label)
        env_layout.addWidget(self.activation_enabled)
        env_layout.addWidget(QLabel('Comando de ativação (source do bashrc)'))
        env_layout.addWidget(self.activation_command)
        probe_row = QHBoxLayout()
        probe_row.addWidget(self.probe_button)
        probe_row.addStretch(1)
        env_layout.addLayout(probe_row)
        env_layout.addWidget(self.probe_label)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(commands_box)
        layout.addWidget(env_box)
        layout.addStretch(1)

    def _initial_probe_hint(self) -> str:
        if self._environment.openfoam_on_path():
            return 'O comando de stage já está no PATH deste processo. A ativação é opcional.'
        if self._environment.suggested_activation_command():
            return 'OpenFOAM não está no PATH. Um bashrc foi encontrado; marque a ativação e verifique o ambiente.'
        if self._environment.host_kind() == 'macos':
            return (
                'OpenFOAM não encontrado neste Mac. Instale o OpenFOAM e informe o source do '
                'etc/bashrc, ou abra a interface a partir de um terminal onde o ambiente já foi carregado.'
            )
        return 'OpenFOAM não encontrado no PATH. Informe o source do etc/bashrc se a interface não herdar o ambiente.'

    def set_probe_result(self, text: str) -> None:
        self.probe_label.setText(text)
