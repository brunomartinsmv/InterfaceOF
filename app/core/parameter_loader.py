from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.models.case_definition import CaseDefinition
from app.models.stage_event import StageChange, StageEvent
from app.utils.normalizer import ensure_valid_token, is_reserved_config_column, normalize_token


@dataclass(slots=True)
class LoadedParameters:
    primary_df: pd.DataFrame
    secondary_df: pd.DataFrame | None
    cases: list[CaseDefinition]
    normalized_primary_columns: dict[str, str]


class ParameterLoader:
    PRIMARY_REQUIRED = {'nome_do_caso'}
    SECONDARY_REQUIRED = {'nome_do_caso', 'tempo', 'variavel', 'valor'}

    def load(self, primary_csv: Path, secondary_csv: Path | None = None) -> LoadedParameters:
        primary_df = pd.read_csv(primary_csv)
        self._ensure_required_columns(primary_df.columns, self.PRIMARY_REQUIRED, 'CSV primário')
        normalized_primary = self._normalize_columns(primary_df.columns)
        primary_df = primary_df.rename(columns=normalized_primary)

        secondary_df = None
        if secondary_csv is not None:
            secondary_df = pd.read_csv(secondary_csv)
            self._ensure_required_columns(secondary_df.columns, self.SECONDARY_REQUIRED, 'CSV secundário')
            normalized_secondary = self._normalize_columns(secondary_df.columns)
            secondary_df = secondary_df.rename(columns=normalized_secondary)
            if 'stage' not in secondary_df.columns:
                secondary_df['stage'] = ''
            secondary_df['variavel'] = secondary_df['variavel'].map(ensure_valid_token)
            self._validate_secondary_values(secondary_df)

        cases = self._build_case_definitions(primary_df, secondary_df)
        return LoadedParameters(primary_df, secondary_df, cases, normalized_primary)

    def _ensure_required_columns(self, columns: Iterable[str], required: set[str], label: str) -> None:
        normalized = {normalize_token(c) for c in columns}
        missing = required - normalized
        if missing:
            raise ValueError(f'{label} sem colunas obrigatórias: {sorted(missing)}')

    def _normalize_columns(self, columns: Iterable[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        seen: dict[str, str] = {}
        for col in columns:
            normalized = normalize_token(col)
            if not normalized:
                raise ValueError(f'Coluna vazia/inválida: {col!r}')
            if normalized in seen and seen[normalized] != col:
                raise ValueError(
                    f'Colunas colidem após normalização: {seen[normalized]!r} e {col!r} -> {normalized!r}'
                )
            seen[normalized] = col
            mapping[col] = normalized
        return mapping

    def _validate_secondary_values(self, df: pd.DataFrame) -> None:
        if df[['nome_do_caso', 'tempo', 'variavel', 'valor']].isnull().any().any():
            raise ValueError('CSV secundário contém campos vazios.')
        for case_name, group in df.groupby('nome_do_caso', sort=False):
            tempos = group['tempo'].astype(float).tolist()
            if any(b < a for a, b in zip(tempos, tempos[1:])):
                raise ValueError(f'Tempo decrescente detectado no CSV secundário para o caso {case_name!r}.')

    def _build_case_definitions(self, primary_df: pd.DataFrame, secondary_df: pd.DataFrame | None) -> list[CaseDefinition]:
        cases: list[CaseDefinition] = []
        secondary_map = self._group_secondary_events(secondary_df) if secondary_df is not None else {}

        for _, row in primary_df.iterrows():
            case_name = str(row['nome_do_caso']).strip()
            if not case_name:
                raise ValueError('nome_do_caso vazio no CSV primário.')
            config_parameters: dict[str, str] = {}
            template_parameters: dict[str, str] = {}
            for col, value in row.items():
                if col == 'nome_do_caso':
                    continue
                if pd.isna(value) or str(value).strip() == '':
                    raise ValueError(f'Parâmetro vazio no CSV primário: caso={case_name}, coluna={col}')
                if is_reserved_config_column(col):
                    config_parameters[col] = str(value)
                else:
                    template_parameters[ensure_valid_token(col)] = str(value)
            stages = secondary_map.get(case_name, [])
            cases.append(CaseDefinition(case_name=case_name, template_parameters=template_parameters,
                                        config_parameters=config_parameters, stages=stages))
        return cases

    def _group_secondary_events(self, df: pd.DataFrame) -> dict[str, list[StageEvent]]:
        if df is None or df.empty:
            return {}
        events_by_case: dict[str, list[StageEvent]] = {}
        for case_name, group in df.groupby('nome_do_caso', sort=False):
            grouped: dict[tuple[float, str], list[StageChange]] = {}
            for _, row in group.iterrows():
                key = (float(row['tempo']), str(row.get('stage', '')).strip())
                grouped.setdefault(key, []).append(StageChange(parameter=row['variavel'], value=str(row['valor'])))
            ordered_events: list[StageEvent] = []
            for idx, ((tempo, stage_label), changes) in enumerate(grouped.items(), start=1):
                label = stage_label or f'stage_{idx}'
                ordered_events.append(StageEvent(case_name=case_name, target_time=tempo,
                                                 stage_label=label, changes=changes))
            ordered_events.sort(key=lambda evt: evt.target_time)
            events_by_case[str(case_name)] = ordered_events
        return events_by_case
