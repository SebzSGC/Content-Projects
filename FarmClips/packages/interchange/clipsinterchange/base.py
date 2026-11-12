"""Contratos base e interfaces para exportadores de timeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from clipseditplan import EditPlan


@dataclass
class FidelityWarning:
    """Advertencia sobre propiedades que no pudieron traducirse 1:1 al NLE destino."""
    field: str
    message: str
    severity: str = "warning"  # "info" | "warning" | "error"


@dataclass
class ExportContext:
    """Contexto y medios necesarios para la exportación."""
    gameplay_path: Path
    camera_path: Path
    camera_offset_s: float = 0.0          # Offset FFT: camera_time = game_time + camera_offset_s
    source_fps: Fraction = Fraction(60, 1)
    voice_spans: List[Tuple[float, float]] = field(default_factory=list)
    clip_id: str = ""
    session_id: str = ""
    captions_mode: str = "native"         # "native" | "overlay"
    assets_dir: Optional[Path] = None


@dataclass
class ExportResult:
    """Resultado de la exportación de un timeline."""
    project_path: Path
    exporter: str
    exporter_version: str
    plan_hash: str
    duration_s: float
    warnings: List[FidelityWarning] = field(default_factory=list)


class TimelineExporter(Protocol):
    """Protocolo estándar para conversores de EditPlan a proyectos NLE."""
    name: str
    version: str

    def export(self, plan: EditPlan, ctx: ExportContext, out_dir: Path) -> ExportResult:
        """Exporta un EditPlan a la carpeta especificada."""
        ...
