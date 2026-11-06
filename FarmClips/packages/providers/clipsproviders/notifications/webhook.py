"""Delivery webhook notifications (Discord embeds, Slack Incoming Webhooks, or generic HTTP JSON)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence

import httpx


def detect_webhook_format(url: str) -> str:
    low = url.lower()
    if "discord.com/api/webhooks" in low or "discordapp.com/api/webhooks" in low:
        return "discord"
    if "hooks.slack.com/" in low:
        return "slack"
    return "generic"


def build_webhook_payload(
    fmt: str,
    session_id: str,
    title: str,
    clips: Sequence[Dict[str, Any]],
    public_web_url: str = "http://127.0.0.1:3040",
) -> Dict[str, Any]:
    base_url = public_web_url.rstrip("/")
    session_url = f"{base_url}/sessions/{session_id}"
    top_clips = list(clips)[:5]

    if fmt == "discord":
        lines: List[str] = []
        for idx, c in enumerate(top_clips, start=1):
            cid = c.get("id", "")
            score = float(c.get("final_score") or c.get("score") or 0.0)
            otitle = c.get("overlay_title") or c.get("post_title") or cid
            lines.append(f"**#{idx}** `{score:.0f}/100` — {otitle} ([Editar]({base_url}/editor/{cid}))")
        desc = "\n".join(lines) if lines else "Sesión completada sin clips automáticos."
        return {
            "username": "ClipsApp",
            "embeds": [
                {
                    "title": f"🎬 Sesión lista: {title}",
                    "url": session_url,
                    "description": desc,
                    "color": 0xFFD400,
                    "footer": {"text": f"ClipsApp • {len(clips)} clips curados • ID {session_id}"},
                }
            ],
        }

    if fmt == "slack":
        bullet = "\n".join(
            f"• *#{idx}* ({float(c.get('final_score') or 0.0):.0f}/100): {c.get('overlay_title') or c.get('post_title')} — <{base_url}/editor/{c.get('id')}|Abrir editor>"
            for idx, c in enumerate(top_clips, start=1)
        )
        return {
            "text": f"🎬 *ClipsApp — Sesión entregada:* <{session_url}|{title}> ({len(clips)} clips)\n{bullet}".strip()
        }

    return {
        "event": "session.delivered",
        "session_id": session_id,
        "title": title,
        "session_url": session_url,
        "clips_count": len(clips),
        "clips": [
            {
                "id": c.get("id"),
                "overlay_title": c.get("overlay_title"),
                "post_title": c.get("post_title"),
                "final_score": c.get("final_score"),
                "editor_url": f"{base_url}/editor/{c.get('id')}",
                "has_final": bool(c.get("has_final") or c.get("final_mp4_path")),
            }
            for c in top_clips
        ],
    }


async def send_delivery_webhook(
    webhook_url: str,
    session_id: str,
    title: str,
    clips: Sequence[Dict[str, Any]],
    public_web_url: str = "http://127.0.0.1:3040",
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Send delivery webhook notification with 1 transient retry; returns delivery status dict."""
    url = webhook_url.strip()
    if not url:
        return {"ok": False, "skipped": True, "reason": "empty_url"}

    fmt = detect_webhook_format(url)
    payload = build_webhook_payload(fmt, session_id=session_id, title=title, clips=clips, public_web_url=public_web_url)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=12.0)
    try:
        last_status = 0
        for attempt in range(2):
            res = await http.post(url, json=payload)
            last_status = res.status_code
            if 200 <= res.status_code < 300:
                return {"ok": True, "status_code": res.status_code, "format": fmt}
            if res.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                await asyncio.sleep(0.5)
                continue
            return {"ok": False, "status_code": res.status_code, "format": fmt, "detail": res.text[:240]}
        return {"ok": False, "status_code": last_status, "format": fmt}
    finally:
        if owns_client:
            await http.aclose()
