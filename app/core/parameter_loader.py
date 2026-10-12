from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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

    @staticmethod
    def sanitize_case_name(name: Any) -> str:
        if pd.isna(name):
            raise ValueError('nome_do_caso vazio ou inválido no CSV primário.')
        cleaned = str(name).strip()
        if not cleaned or cleaned.lower() == 'nan':
            raise ValueError('nome_do_caso vazio no CSV primário.')
        if '/' in cleaned or '\\' in cleaned or cleaned in ('.', '..') or '..' in cleaned:
            raise ValueError(f'nome_do_caso inválido (contém separador ou travessia de diretório): {cleaned!r}')
        invalid_chars = set('<>:"|?*\0')
        if any(c in invalid_chars for c in cleaned):
            raise ValueError(f'nome_do_caso contém caracteres proibidos: {cleaned!r}')
        return cleaned

    def _read_raw_headers(self, csv_path: Path) -> list[str]:
        with csv_path.open('r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                raise ValueError(f'Arquivo CSV vazio ou sem cabeçalho: {csv_path.name}')
            seen: set[str] = set()
            for col in header:
                cleaned = col.strip()
                if cleaned in seen:
                    raise ValueError(f'Cabeçalho duplicado no arquivo {csv_path.name}: {cleaned!r}')
                seen.add(cleaned)
            return header

    def load(self, primary_csv: Path, secondary_csv: Path | None = None) -> LoadedParameters:
        self._read_raw_headers(primary_csv)
        primary_df = pd.read_csv(primary_csv)
        self._ensure_required_columns(primary_df.columns, self.PRIMARY_REQUIRED, 'CSV primário')
        normalized_primary = self._normalize_columns(primary_df.columns)
        primary_df = primary_df.rename(columns=normalized_primary)

        secondary_df = None
        if secondary_csv is not None:
            self._read_raw_headers(secondary_csv)
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

    def _normalize_column_name(self, col: str) -> str:
        raw = str(col).strip()
        if is_reserved_config_column(raw):
            remainder = normalize_token(raw[5:])
            return f'cfg__{remainder}'
        return normalize_token(raw)

    def _normalize_columns(self, columns: Iterable[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        seen: dict[str, str] = {}
        for col in columns:
            normalized = self._normalize_column_name(col)
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
            self.sanitize_case_name(case_name)
            try:
                tempos = [float(t) for t in group['tempo']]
            except (ValueError, TypeError):
                raise ValueError(f'Tempo inválido detectado no CSV secundário para o caso {case_name!r}.')
            if any(b < a for a, b in zip(tempos, tempos[1:])):
                raise ValueError(f'Tempo decrescente detectado no CSV secundário para o caso {case_name!r}.')

    def _build_case_definitions(self, primary_df: pd.DataFrame, secondary_df: pd.DataFrame | None) -> list[CaseDefinition]:
        cases: list[CaseDefinition] = []
        secondary_map = self._group_secondary_events(secondary_df) if secondary_df is not None else {}
        seen_cases: set[str] = set()

        for _, row in primary_df.iterrows():
            case_name = self.sanitize_case_name(row['nome_do_caso'])
            if case_name in seen_cases:
                raise ValueError(f'Caso duplicado no CSV primário: {case_name!r}')
            seen_cases.add(case_name)

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

        if secondary_df is not None and not secondary_df.empty:
            for sec_case in secondary_df['nome_do_caso'].unique():
                sec_cleaned = self.sanitize_case_name(sec_case)
                if sec_cleaned not in seen_cases:
                    raise ValueError(f'Caso {sec_cleaned!r} no CSV secundário não existe no CSV primário.')

        return cases

    def _group_secondary_events(self, df: pd.DataFrame) -> dict[str, list[StageEvent]]:
        if df is None or df.empty:
            return {}
        events_by_case: dict[str, list[StageEvent]] = {}
        for case_name, group in df.groupby('nome_do_caso', sort=False):
            case_key = self.sanitize_case_name(case_name)
            tempo_groups: dict[float, dict[str, Any]] = {}
            for _, row in group.iterrows():
                try:
                    tempo = float(row['tempo'])
                except (ValueError, TypeError):
                    raise ValueError(f'Tempo inválido no CSV secundário para o caso {case_name!r}: {row["tempo"]!r}')
                if not (tempo >= 0.0) or pd.isna(tempo):
                    raise ValueError(f'Tempo negativo ou inválido no CSV secundário para o caso {case_name!r}: {tempo}')

                label = str(row.get('stage', '')).strip()
                if tempo not in tempo_groups:
                    tempo_groups[tempo] = {'label': label, 'changes': []}
                elif label and not tempo_groups[tempo]['label']:
                    tempo_groups[tempo]['label'] = label

                tempo_groups[tempo]['changes'].append(
                    StageChange(parameter=row['variavel'], value=str(row['valor']))
                )

            ordered_events: list[StageEvent] = []
            for idx, (tempo, data) in enumerate(sorted(tempo_groups.items(), key=lambda x: x[0]), start=1):
                label = data['label'] or f'stage_{idx}'
                ordered_events.append(
                    StageEvent(case_name=case_key, target_time=tempo, stage_label=label, changes=data['changes'])
                )
            events_by_case[case_key] = ordered_events
        return events_by_case
