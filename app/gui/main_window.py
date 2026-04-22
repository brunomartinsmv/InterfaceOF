from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from app.core.campaign_manager import CampaignManager
from app.gui.tabs_execution import ExecutionTab
from app.gui.tabs_monitor import MonitorTab
from app.gui.tabs_project import ProjectTab
from app.gui.tabs_settings import SettingsTab
from app.models.project_config import ProjectConfig


class CampaignWorker(QObject):
    log_line = Signal(str)
    residual_batch = Signal(object)
    time_update = Signal(object)
    status_message = Signal(str)
    case_status = Signal(str, str)
    command_started = Signal(str, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: CampaignManager, config: ProjectConfig) -> None:
        super().__init__()
        self.manager = manager
        self.config = config
        self._residual_buffer: list[dict[str, object]] = []
        self._last_residual_emit = time.monotonic()
        self._emit_interval_seconds = 0.35
        self._emit_batch_size = 120

    def _handle_residual(self, equation: str, value: float, source_log: str, time_value: float | None) -> None:
        self._residual_buffer.append({
            'equation': equation,
            'value': value,
            'source_log': source_log,
            'time': time_value,
        })
        now = time.monotonic()
        if len(self._residual_buffer) >= self._emit_batch_size or (now - self._last_residual_emit) >= self._emit_interval_seconds:
            self._flush_residuals()

    def _flush_residuals(self) -> None:
        if not self._residual_buffer:
            return
        payload = list(self._residual_buffer)
        self._residual_buffer.clear()
        self._last_residual_emit = time.monotonic()
        self.residual_batch.emit(payload)


    def _handle_command_started(self, label: str, log_path: str) -> None:
        self._flush_residuals()
        self.command_started.emit(label, log_path)

    def run(self) -> None:
        try:
            campaign_dir = self.manager.run_campaign(
                self.config,
                stdout_callback=lambda line: self.log_line.emit(line),
                residual_callback=self._handle_residual,
                status_callback=lambda status: (self.status_message.emit(f'{status.case_name}: {status.status}'), self.case_status.emit(status.case_name, status.status)),
                time_callback=lambda value: self.time_update.emit(value),
                command_started_callback=self._handle_command_started,
            )
            self._flush_residuals()
            self.finished.emit(str(campaign_dir))
        except Exception as exc:  # noqa: BLE001
            self._flush_residuals()
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('OpenFOAM Campaign v0.3')
        self.resize(1100, 750)

        self.manager = CampaignManager()
        self.project_tab = ProjectTab()
        self.settings_tab = SettingsTab()
        self.execution_tab = ExecutionTab()
        self.monitor_tab = MonitorTab()
        self.footer_label = QLabel('Pronto.')
        self.worker_thread: QThread | None = None
        self.worker: CampaignWorker | None = None

        self.tabs = QTabWidget()
        self.tabs.addTab(self.project_tab, 'Projeto')
        self.tabs.addTab(self.settings_tab, 'Configuração')
        self.tabs.addTab(self.execution_tab, 'Execução')
        self.tabs.addTab(self.monitor_tab, 'Monitoramento')
        self.tabs.currentChanged.connect(self._on_tab_changed)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tabs)
        layout.addWidget(self.footer_label)
        self.setCentralWidget(central)

        self.project_tab.validate_button.clicked.connect(self.validate_project)
        self.execution_tab.run_button.clicked.connect(self.run_campaign)
        self.execution_tab.stop_button.clicked.connect(self.stop_case)
        self.execution_tab.open_case_requested.connect(self.open_case_in_paraview)
        self.execution_tab.open_all_requested.connect(self.open_all_cases_in_paraview)
        self._on_tab_changed(self.tabs.currentIndex())

    def _multiline_commands(self, text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def build_config(self) -> ProjectConfig:
        secondary = self.project_tab.secondary_csv_edit.text().strip()
        return ProjectConfig(
            base_case_dir=Path(self.project_tab.base_case_edit.text().strip()) if self.project_tab.base_case_edit.text().strip() else None,
            primary_csv=Path(self.project_tab.primary_csv_edit.text().strip()) if self.project_tab.primary_csv_edit.text().strip() else None,
            secondary_csv=Path(secondary) if secondary else None,
            output_dir=Path(self.project_tab.output_dir_edit.text().strip()) if self.project_tab.output_dir_edit.text().strip() else None,
            runner_mode='internal',
            default_solver='foamRun',
            n_processors=1,
            directory_prefix=self.settings_tab.dir_prefix.text().strip() or 'case_',
            log_prefix=self.settings_tab.log_prefix.text().strip() or 'log_',
            shell_executable='',
            activation_enabled=False,
            activation_mode='none',
            activation_command='',
            bashrc_path='~/.bashrc',
            internal_setup_commands=self._multiline_commands(self.settings_tab.setup_commands.toPlainText()),
            internal_stage_commands=self._multiline_commands(self.settings_tab.stage_commands.toPlainText()) or ['foamRun'],
            internal_post_commands=self._multiline_commands(self.settings_tab.post_commands.toPlainText()),
            plot_time_stride=float(self.settings_tab.plot_time_stride.value()),
            plot_iteration_stride=max(1, int(self.settings_tab.plot_iteration_stride.value())),
        )

    def _on_tab_changed(self, index: int) -> None:
        if not hasattr(self, 'tabs'):
            return
        current = self.tabs.widget(index)
        self.execution_tab.set_active(current is self.execution_tab)
        self.monitor_tab.set_active(current is self.monitor_tab)

    def validate_project(self) -> None:
        try:
            config = self.build_config()
            report = self.manager.validate_project(config)
            self.project_tab.populate_audit_table(report.audit_rows)
            issues_text = '\n'.join(f'[{i.severity}] {i.message}' for i in report.issues) if report.issues else 'Sem inconsistências.'
            self.project_tab.validation_label.setText(issues_text)
            if self.manager.loaded_parameters:
                self.execution_tab.populate_queue(self.manager.loaded_parameters.cases)
            self.footer_label.setText('Validação concluída.' if report.ok else 'Validação encontrou erros.')
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, 'Erro na validação', str(exc))
            self.footer_label.setText('Falha na validação.')

    def run_campaign(self) -> None:
        try:
            config = self.build_config()
            if self.worker_thread is not None:
                QMessageBox.warning(self, 'Execução', 'Já existe uma campanha em execução.')
                return
            self.execution_tab.clear_console()
            self.execution_tab.reset_statuses()
            self.monitor_tab.set_plot_config(
                float(self.settings_tab.plot_time_stride.value()),
                max(1, int(self.settings_tab.plot_iteration_stride.value())),
            )
            self.monitor_tab.reset()
            self.monitor_tab.set_status('starting')
            self.worker_thread = QThread(self)
            self.worker = CampaignWorker(self.manager, config)
            self.worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.worker.run)
            self.worker.log_line.connect(self.execution_tab.append_console)
            self.worker.residual_batch.connect(self.monitor_tab.ingest_residual_batch)
            self.worker.time_update.connect(self.monitor_tab.set_time)
            self.worker.command_started.connect(self.monitor_tab.set_active_command)
            self.worker.status_message.connect(self.monitor_tab.set_status)
            self.worker.case_status.connect(self.execution_tab.update_case_status)
            self.worker.finished.connect(self._on_run_finished)
            self.worker.failed.connect(self._on_run_failed)
            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.failed.connect(self.worker_thread.quit)
            self.worker_thread.finished.connect(self._cleanup_worker)
            self.worker_thread.start()
            self.footer_label.setText('Campanha em execução...')
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, 'Erro ao iniciar campanha', str(exc))

    def stop_case(self) -> None:
        self.manager.runner.stop_case()
        self.footer_label.setText('Solicitado encerramento do caso atual.')

    def open_case_in_paraview(self, case_name: str) -> None:
        payload = self.execution_tab.case_outputs.get(case_name)
        if not payload:
            QMessageBox.warning(self, 'ParaView', f'Case ainda não disponível: {case_name}')
            return
        case_dir = Path(payload['case_dir'])
        try:
            self.manager.paraview_launcher.open_case(case_dir)
            self.footer_label.setText(f'Abrindo ParaView para {case_name}...')
        except FileNotFoundError:
            QMessageBox.critical(self, 'ParaView', 'Comando paraview não encontrado no ambiente atual.')
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, 'ParaView', f'Falha ao abrir {case_name}:\n{exc}')

    def open_all_cases_in_paraview(self) -> None:
        foam_files = [Path(v['foam_file']) for v in self.execution_tab.case_outputs.values() if v.get('foam_file')]
        campaign_dir = self.manager.last_campaign_dir
        if not campaign_dir or not foam_files:
            self.footer_label.setText('Nenhum case disponível para abrir em conjunto.')
            return
        try:
            _proc, script_path = self.manager.paraview_launcher.open_cases_in_single_paraview(campaign_dir, foam_files)
            self.footer_label.setText(f'Abrindo ParaView com {len(foam_files)} case(s)... Script: {script_path.name}')
        except FileNotFoundError:
            self.footer_label.setText('Comando paraview não encontrado no ambiente atual.')
        except Exception as exc:  # noqa: BLE001
            self.footer_label.setText(f'Falha ao abrir cases em conjunto: {exc}')
            print(f'Falha ao abrir cases em conjunto: {exc}')

    def _on_run_finished(self, campaign_dir: str) -> None:
        self.execution_tab.apply_case_outputs_from_statuses(self.manager.statuses)
        self.footer_label.setText(f'Campanha finalizada: {campaign_dir}')

    def _on_run_failed(self, message: str) -> None:
        self.footer_label.setText('Campanha falhou.')
        QMessageBox.critical(self, 'Falha na campanha', message)

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
