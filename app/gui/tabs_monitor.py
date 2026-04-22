from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class MonitorTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.status_label = QLabel('Status: idle')
        self.time_label = QLabel('Tempo atual: -')
        self.command_label = QLabel('Comando atual: -')
        self.log_label = QLabel('Log atual: -')
        self.mode_label = QLabel('Plot: amostra/iteração | N = 1')
        self.residual_table = QTableWidget(0, 3)
        self.residual_table.setHorizontalHeaderLabels(['equation', 'last_initial_residual', 'source_log'])

        self.figure = Figure(figsize=(6, 4), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)

        self._latest_residuals: dict[str, dict[str, str | float | None]] = {}
        self._residual_history: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=300))
        self._residual_timestep_cache: dict[str, dict[str, float]] = defaultdict(dict)
        self._last_flushed_time_by_eq: dict[str, float] = {}
        self._plotted_count_by_eq: dict[str, int] = defaultdict(int)
        self._last_plotted_time_by_eq: dict[str, float] = {}
        self._active_log_path = ''
        self._active_log_name = ''
        self._dirty_table = False
        self._dirty_plot = False
        self._dirty_selector = False
        self._active = False
        self._plot_enabled: dict[str, bool] = {}
        self._plot_checkboxes: dict[str, QCheckBox] = {}
        self._plot_time_stride = 0.0
        self._plot_iteration_stride = 1

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1200)
        self._refresh_timer.timeout.connect(self._refresh_ui)

        selector_label = QLabel('Resíduos plotados:')
        self.selector_container = QWidget()
        self.selector_layout = QHBoxLayout(self.selector_container)
        self.selector_layout.setContentsMargins(0, 0, 0, 0)
        self.selector_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.selector_layout.addStretch(1)
        self.selector_scroll = QScrollArea()
        self.selector_scroll.setWidgetResizable(True)
        self.selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.selector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.selector_scroll.setMaximumHeight(60)
        self.selector_scroll.setWidget(self.selector_container)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.command_label)
        layout.addWidget(self.log_label)
        layout.addWidget(self.mode_label)
        layout.addWidget(selector_label)
        layout.addWidget(self.selector_scroll)
        layout.addWidget(self.canvas)
        layout.addWidget(self.residual_table)
        self._init_plot()

    def set_plot_config(self, time_stride: float, iteration_stride: int) -> None:
        self._plot_time_stride = max(0.0, float(time_stride))
        self._plot_iteration_stride = max(1, int(iteration_stride))
        if self._plot_time_stride > 0:
            self.mode_label.setText(f'Plot: tempo | Δt mínimo = {self._plot_time_stride:g} s')
        else:
            self.mode_label.setText(f'Plot: amostra/iteração | N = {self._plot_iteration_stride}')
        self._dirty_plot = True
        if self._active:
            self._refresh_ui(force=True)

    def _using_time_axis(self) -> bool:
        return self._plot_time_stride > 0

    def _init_plot(self) -> None:
        self.ax.clear()
        self.ax.set_title('Resíduos da run atual')
        self.ax.set_xlabel('Time (s)' if self._using_time_axis() else 'Amostra/iteração exibida')
        self.ax.set_ylabel('Initial residual')
        self.ax.set_yscale('log')
        self.ax.grid(True, which='both', alpha=0.3)
        self.canvas.draw_idle()

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._refresh_timer.start()
            self._refresh_ui(force=True)
        else:
            self._refresh_timer.stop()

    def reset(self) -> None:
        self.set_time(None)
        self.set_status('idle')
        self.set_active_command('-', '-')

    def set_status(self, text: str) -> None:
        self.status_label.setText(f'Status: {text}')

    def set_time(self, value: float | None) -> None:
        text = '-' if value is None else str(value)
        self.time_label.setText(f'Tempo atual: {text}')

    def set_active_command(self, command_label: str, log_path: str) -> None:
        self.command_label.setText(f'Comando atual: {command_label}')
        self.log_label.setText(f'Log atual: {Path(log_path).name if log_path not in {"-", ""} else log_path}')
        self._active_log_path = log_path
        self._active_log_name = Path(log_path).name if log_path not in {'-', ''} else ''
        self._latest_residuals.clear()
        self._residual_history.clear()
        self._residual_timestep_cache.clear()
        self._last_flushed_time_by_eq.clear()
        self._plotted_count_by_eq.clear()
        self._last_plotted_time_by_eq.clear()
        self._plot_enabled.clear()
        self._clear_plot_checkboxes()
        self._dirty_selector = True
        self._dirty_table = True
        self._dirty_plot = True
        self.residual_table.setRowCount(0)
        if self._active:
            self._refresh_ui(force=True)

    def _clear_plot_checkboxes(self) -> None:
        while self.selector_layout.count() > 1:
            item = self.selector_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._plot_checkboxes.clear()

    def _ensure_checkbox(self, equation: str) -> None:
        if equation in self._plot_checkboxes:
            return
        checkbox = QCheckBox(equation)
        checkbox.setChecked(False)
        checkbox.toggled.connect(lambda checked, eq=equation: self._on_plot_toggle(eq, checked))
        self.selector_layout.insertWidget(max(0, self.selector_layout.count() - 1), checkbox)
        self._plot_checkboxes[equation] = checkbox
        self._plot_enabled[equation] = False
        self._dirty_selector = True

    def _on_plot_toggle(self, equation: str, checked: bool) -> None:
        self._plot_enabled[equation] = checked
        self._dirty_plot = True
        if self._active:
            self._refresh_ui(force=False)

    def _accept_point(self, equation: str, time_value: float | None, value: float) -> None:
        self._plotted_count_by_eq[equation] += 1
        point_index = self._plotted_count_by_eq[equation]
        if self._using_time_axis() and time_value is not None:
            last_time = self._last_plotted_time_by_eq.get(equation)
            if last_time is None or (time_value - last_time) >= self._plot_time_stride:
                self._residual_history[equation].append((time_value, value))
                self._last_plotted_time_by_eq[equation] = time_value
                self._dirty_plot = True
            return

        if point_index == 1 or ((point_index - 1) % self._plot_iteration_stride == 0):
            self._residual_history[equation].append((float(point_index), value))
            self._dirty_plot = True

    def ingest_residual_batch(self, batch: object) -> None:
        if not isinstance(batch, list):
            return
        for entry in batch:
            try:
                equation = str(entry['equation'])
                value = float(entry['value'])
                source_log = str(entry['source_log'])
                time_value = entry.get('time')
                time_value = float(time_value) if time_value is not None else None
            except Exception:
                continue
            source_log_name = Path(source_log).name
            if self._active_log_name and source_log_name != self._active_log_name:
                continue
            self._ensure_checkbox(equation)
            self._latest_residuals[equation] = {
                'value': value,
                'source_log': source_log_name,
                'time': time_value,
            }
            if time_value is not None:
                self._residual_timestep_cache[equation][str(time_value)] = value
                last_time = self._last_flushed_time_by_eq.get(equation)
                if last_time is None:
                    self._last_flushed_time_by_eq[equation] = time_value
                elif time_value > last_time:
                    prev_key = str(last_time)
                    if prev_key in self._residual_timestep_cache[equation]:
                        prev_value = self._residual_timestep_cache[equation].pop(prev_key)
                        self._accept_point(equation, last_time, prev_value)
                    self._last_flushed_time_by_eq[equation] = time_value
            else:
                self._accept_point(equation, None, value)
            self._dirty_table = True
        if self._active:
            self._refresh_ui(force=False)

    def _refresh_ui(self, force: bool = False) -> None:
        if not self._active and not force:
            return
        if self._dirty_table or force:
            self._refresh_table()
        if self._dirty_plot or force:
            self._refresh_plot()

    def _refresh_table(self) -> None:
        items = list(self._latest_residuals.items())
        self.residual_table.setUpdatesEnabled(False)
        self.residual_table.setRowCount(len(items))
        for row_idx, (eq, payload) in enumerate(items):
            self.residual_table.setItem(row_idx, 0, QTableWidgetItem(eq))
            self.residual_table.setItem(row_idx, 1, QTableWidgetItem(f"{payload['value']:.6g}"))
            self.residual_table.setItem(row_idx, 2, QTableWidgetItem(str(payload['source_log'])))
        self.residual_table.setUpdatesEnabled(True)
        self._dirty_table = False

    def _preview_point(self, equation: str) -> tuple[float, float] | None:
        latest = self._latest_residuals.get(equation)
        if not latest:
            return None
        value = float(latest['value'])
        time_value = latest.get('time')
        if self._using_time_axis() and time_value is not None:
            return float(time_value), value
        return float(self._plotted_count_by_eq.get(equation, 0) + 1), value

    def _refresh_plot(self) -> None:
        self.ax.clear()
        self.ax.set_title('Resíduos da run atual')
        self.ax.set_xlabel('Time (s)' if self._using_time_axis() else 'Amostra/iteração exibida')
        self.ax.set_ylabel('Initial residual')
        self.ax.set_yscale('log')
        self.ax.grid(True, which='both', alpha=0.3)
        plotted = False
        for equation, enabled in self._plot_enabled.items():
            if not enabled:
                continue
            values = list(self._residual_history.get(equation, []))
            preview = self._preview_point(equation)
            if preview is not None:
                if not values or values[-1][0] != preview[0]:
                    values = values + [preview]
            filtered = [(x, y) for x, y in values if y > 0]
            if not filtered:
                continue
            xs = [x for x, _ in filtered]
            ys = [y for _, y in filtered]
            self.ax.plot(xs, ys, label=equation, linewidth=1.0)
            plotted = True
        if plotted:
            self.ax.legend(loc='best')
        else:
            self.ax.text(0.5, 0.5, 'Selecione resíduos para plotar', ha='center', va='center', transform=self.ax.transAxes)
        self.canvas.draw_idle()
        self._dirty_plot = False
