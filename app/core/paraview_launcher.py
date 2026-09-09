from __future__ import annotations

import glob
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from app.utils.file_ops import ensure_dir, write_text


class ParaViewLauncher:
    def ensure_case_foam(self, case_dir: Path, case_name: str) -> Path:
        foam_file = case_dir / f"{case_name}.foam"
        foam_file.touch(exist_ok=True)
        return foam_file

    def resolve_paraview_binary(self) -> str | None:
        found = shutil.which('paraview')
        if found:
            return found
        apps = sorted(glob.glob('/Applications/ParaView*.app/Contents/MacOS/paraview'), reverse=True)
        if apps:
            return apps[0]
        return None

    def _paraview_command(self, *args: str) -> list[str]:
        binary = self.resolve_paraview_binary()
        if not binary:
            raise FileNotFoundError('Comando paraview não encontrado no PATH nem em /Applications.')
        return [binary, *args]

    def open_case(self, case_dir: Path, foam_file: Path | None = None) -> subprocess.Popen:
        target = foam_file if foam_file is not None else self.ensure_case_foam(case_dir, case_dir.name)
        return subprocess.Popen(
            self._paraview_command(f'--data={target}'),
            cwd=str(case_dir),
            start_new_session=True,
        )

    def build_open_many_script(self, campaign_dir: Path, foam_files: Iterable[Path]) -> Path:
        logs_dir = ensure_dir(campaign_dir / 'logs')
        script_path = logs_dir / 'open_cases_in_paraview.py'
        file_lines = ',\n    '.join(repr(str(path)) for path in foam_files)
        script = (
            'from paraview.simple import *\n\n'
            'foam_files = [\n'
            f'    {file_lines}\n'
            ']\n\n'
            'view = GetActiveViewOrCreate("RenderView")\n'
            'readers = []\n'
            'for idx, foam_file in enumerate(foam_files):\n'
            '    reader = OpenDataFile(foam_file)\n'
            '    if reader is None:\n'
            '        print(f"Falha ao abrir: {foam_file}")\n'
            '        continue\n'
            '    readers.append(reader)\n'
            '    try:\n'
            '        RenameSource(f"case_{idx+1}", reader)\n'
            '    except Exception:\n'
            '        pass\n'
            '    try:\n'
            '        Show(reader, view)\n'
            '    except Exception:\n'
            '        Show(reader)\n'
            '    try:\n'
            '        reader.UpdatePipeline()\n'
            '    except Exception:\n'
            '        try:\n'
            '            UpdatePipeline(proxy=reader)\n'
            '        except Exception:\n'
            '            pass\n\n'
            'try:\n'
            '    scene = GetAnimationScene()\n'
            '    scene.UpdateAnimationUsingDataTimeSteps()\n'
            'except Exception as exc:\n'
            '    print(f"Falha ao atualizar timeline: {exc}")\n\n'
            'try:\n'
            '    ResetCamera(view)\n'
            'except Exception:\n'
            '    pass\n'
            'RenderAllViews()\n'
        )
        write_text(script_path, script)
        return script_path

    def open_cases_in_single_paraview(self, campaign_dir: Path, foam_files: Iterable[Path]) -> tuple[subprocess.Popen, Path]:
        script_path = self.build_open_many_script(campaign_dir, foam_files)
        proc = subprocess.Popen(
            self._paraview_command(f'--script={script_path}'),
            cwd=str(campaign_dir),
            start_new_session=True,
        )
        return proc, script_path
