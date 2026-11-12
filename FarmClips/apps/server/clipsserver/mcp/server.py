"""Servidor Model Context Protocol (MCP) oficial de FarmClips en transporte stdio."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from clipseditplan import EditPlan
from mcp.server.mcpserver import MCPServer

DEFAULT_API_URL = "http://127.0.0.1:8790"


def get_api_base_url() -> str:
    return os.environ.get("FARMCLIPS_API", DEFAULT_API_URL).rstrip("/")


def _api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    base = get_api_base_url()
    url = f"{base}{endpoint}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 404:
                raise ValueError(f"Recurso no encontrado: {endpoint}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise ConnectionError(
            f"No se pudo conectar a FarmClips en {base}. Asegúrate de que el servidor esté iniciado (infra\\dev.ps1)."
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Error HTTP {e.response.status_code} desde FarmClips: {e.response.text}")


def _api_post(endpoint: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
    base = get_api_base_url()
    url = f"{base}{endpoint}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=json_body or {}, params=params)
            if resp.status_code == 404:
                raise ValueError(f"Recurso no encontrado: {endpoint}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise ConnectionError(
            f"No se pudo conectar a FarmClips en {base}. Asegúrate de que el servidor esté iniciado (infra\\dev.ps1)."
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Error HTTP {e.response.status_code} desde FarmClips: {e.response.text}")


def _api_put(endpoint: str, json_body: Dict[str, Any]) -> Any:
    base = get_api_base_url()
    url = f"{base}{endpoint}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.put(url, json=json_body)
            if resp.status_code == 404:
                raise ValueError(f"Recurso no encontrado: {endpoint}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise ConnectionError(
            f"No se pudo conectar a FarmClips en {base}. Asegúrate de que el servidor esté iniciado (infra\\dev.ps1)."
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Error HTTP {e.response.status_code} desde FarmClips: {e.response.text}")


def create_mcp_server() -> MCPServer:
    """Crea e inicializa el servidor MCP con las 9 herramientas oficiales."""
    server = MCPServer(
        name="farmclips",
        instructions=(
            "FarmClips Copilot: Asistente para edición de video vertical 9:16 de gaming. "
            "Permite consultar sesiones de grabación, inspeccionar y modificar planes de edición "
            "(EditPlan v2 con validación Pydantic), buscar fragmentos de voz en la transcripción, "
            "exportar y abrir proyectos en FilmCraft NLE, y disparar renderizados."
        ),
    )

    @server.tool(name="list_sessions", description="Lista todas las sesiones de grabación en FarmClips.")
    def list_sessions() -> str:
        sessions = _api_get("/sessions")
        summary = []
        for s in sessions:
            summary.append({
                "id": s.get("id"),
                "title": s.get("title"),
                "state": s.get("state"),
                "clips_count": s.get("clips_count", 0),
                "rendered_count": s.get("rendered_count", 0),
                "duration_min": round(s.get("duration_sec", 0) / 60, 1),
            })
        return json.dumps(summary, indent=2, ensure_ascii=False)

    @server.tool(name="list_clips", description="Lista los clips generados para una sesión específica.")
    def list_clips(session_id: str) -> str:
        clips = _api_get(f"/sessions/{session_id}/clips")
        result = []
        for c in clips:
            start = float(c.get("start") or 0.0)
            end = float(c.get("end") or 0.0)
            duration_s = round(end - start, 2) if end > start else c.get("duration_s")
            result.append({
                "clip_id": c.get("id"),
                "title": c.get("post_title") or c.get("overlay_title") or "Sin título",
                "score": c.get("final_score"),
                "duration_s": duration_s,
                "state": c.get("state"),
                "has_final_render": bool(c.get("has_final")),
                "has_draft_render": bool(c.get("has_draft")),
            })
        return json.dumps(result, indent=2, ensure_ascii=False)

    @server.tool(name="get_clip", description="Obtiene los detalles y el EditPlan v2 completo de un clip.")
    def get_clip(clip_id: str) -> str:
        data = _api_get(f"/clips/{clip_id}")
        clip = data.get("clip", {})
        plan = clip.get("editplan")
        start = float(clip.get("start") or 0.0)
        end = float(clip.get("end") or 0.0)
        duration_s = round(end - start, 2) if end > start else clip.get("duration_s")
        return json.dumps({
            "clip_id": clip_id,
            "title": clip.get("post_title") or clip.get("overlay_title"),
            "session_id": clip.get("session_id"),
            "duration_s": duration_s,
            "score": clip.get("final_score"),
            "editplan": plan,
        }, indent=2, ensure_ascii=False)

    @server.tool(
        name="get_transcript",
        description="Obtiene las palabras y frases de la transcripción de una sesión dentro de un rango de tiempo en segundos.",
    )
    def get_transcript(session_id: str, start_sec: float = 0.0, end_sec: float = 3600.0) -> str:
        utterances = _api_get(f"/sessions/{session_id}/utterances")
        filtered = []
        for u in utterances:
            u_start = float(u.get("start", 0.0))
            u_end = float(u.get("end", 0.0))
            if (u_start <= end_sec) and (u_end >= start_sec):
                words = u.get("words") or []
                matching_words = [
                    {"word": w.get("text", ""), "start": w.get("start"), "end": w.get("end")}
                    for w in words
                    if start_sec <= float(w.get("start", 0.0)) <= end_sec
                ]
                filtered.append({
                    "utterance_id": u.get("id"),
                    "speaker": u.get("speaker"),
                    "start": u_start,
                    "end": u_end,
                    "text": u.get("text"),
                    "words": matching_words if matching_words else None,
                })
        return json.dumps(filtered, indent=2, ensure_ascii=False)

    @server.tool(
        name="update_editplan",
        description="Valida con Pydantic y aplica un nuevo EditPlan o parche al clip, notificando a la interfaz web en tiempo real.",
    )
    def update_editplan(clip_id: str, editplan: Dict[str, Any]) -> str:
        # 1. Validación estricta con Pydantic
        try:
            validated = EditPlan.model_validate(editplan)
        except Exception as exc:
            return json.dumps({"error": f"Plan inválido según el contrato EditPlan v2: {exc}"}, ensure_ascii=False)

        # 2. Guardar en el servidor
        res = _api_put(f"/clips/{clip_id}/editplan", validated.model_dump(mode="json", exclude_none=True))
        return json.dumps({
            "ok": True,
            "clip_id": clip_id,
            "message": "EditPlan actualizado y sincronizado en la interfaz web.",
            "plan_hash": res.get("editplan", {}).get("plan_hash", ""),
        }, ensure_ascii=False)

    @server.tool(
        name="export_to_filmcraft",
        description="Exporta el EditPlan del clip a un proyecto nativo FilmCraft (.fcproj) u OTIO en disco.",
    )
    def export_to_filmcraft(clip_id: str, format: str = "filmcraft") -> str:
        res = _api_post(f"/clips/{clip_id}/filmcraft/export", params={"format": format})
        return json.dumps(res, indent=2, ensure_ascii=False)

    @server.tool(
        name="open_in_filmcraft",
        description="Exporta el clip y abre FilmCraft con el timeline montado (reutiliza ventana si está abierta).",
    )
    def open_in_filmcraft(clip_id: str) -> str:
        res = _api_post(f"/clips/{clip_id}/filmcraft/open")
        return json.dumps(res, indent=2, ensure_ascii=False)

    @server.tool(
        name="render_clip",
        description="Encola el renderizado acelerado por GPU de un clip (calidad: 'draft' 540p o 'final' 1080p).",
    )
    def render_clip(clip_id: str, quality: str = "draft") -> str:
        res = _api_post(f"/clips/{clip_id}/render", json_body={"quality": quality, "async_mode": True})
        return json.dumps(res, indent=2, ensure_ascii=False)

    @server.tool(
        name="get_render_status",
        description="Consulta si un clip ya fue renderizado y su estado de procesamiento.",
    )
    def get_render_status(clip_id: str) -> str:
        data = _api_get(f"/clips/{clip_id}")
        clip = data.get("clip", {})
        return json.dumps({
            "clip_id": clip_id,
            "state": clip.get("state"),
            "has_final": bool(clip.get("has_final")),
            "has_draft": bool(clip.get("has_draft")),
        }, indent=2, ensure_ascii=False)

    return server
