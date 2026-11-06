"""Catalog of 42 gaming & reaction emojis rendered as supersampled (2x Lanczos) RGBA PNGs with zero network dependency."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

EMOJI_CATALOG: List[Dict[str, str]] = [
    # Fuego & Hype
    {"id": "1f525", "char": "🔥", "name": "Fuego", "category": "hype"},
    {"id": "26a1", "char": "⚡", "name": "Rayo", "category": "hype"},
    {"id": "1f4a5", "char": "💥", "name": "Explosión", "category": "hype"},
    {"id": "1f4a3", "char": "💣", "name": "Bomba", "category": "hype"},
    {"id": "1f680", "char": "🚀", "name": "Cohete", "category": "hype"},
    {"id": "1f4af", "char": "💯", "name": "Cien puntos", "category": "hype"},
    {"id": "1f6a8", "char": "🚨", "name": "Sirena", "category": "hype"},
    {"id": "1f389", "char": "🎉", "name": "Celebración", "category": "hype"},
    {"id": "1f48e", "char": "💎", "name": "Diamante", "category": "hype"},
    {"id": "1f451", "char": "👑", "name": "Corona", "category": "hype"},
    # Reacciones intensas
    {"id": "1f631", "char": "😱", "name": "Grito / Shock", "category": "reaccion"},
    {"id": "1f92f", "char": "🤯", "name": "Mente volada", "category": "reaccion"},
    {"id": "1f480", "char": "💀", "name": "Calavera", "category": "reaccion"},
    {"id": "1f440", "char": "👀", "name": "Ojos alerta", "category": "reaccion"},
    {"id": "1f976", "char": "🥶", "name": "Sangre fría", "category": "reaccion"},
    {"id": "1f92c", "char": "🤬", "name": "Furia", "category": "reaccion"},
    {"id": "1f624", "char": "😤", "name": "Resoplido", "category": "reaccion"},
    {"id": "1f608", "char": "😈", "name": "Modo diablo", "category": "reaccion"},
    {"id": "1fae1", "char": "🫡", "name": "Respeto / Saludo", "category": "reaccion"},
    {"id": "1f9e0", "char": "🧠", "name": "200 IQ", "category": "reaccion"},
    # Humor y emoción
    {"id": "1f602", "char": "😂", "name": "Risa con lágrimas", "category": "humor"},
    {"id": "1f62d", "char": "😭", "name": "Llanto épico", "category": "humor"},
    {"id": "1f921", "char": "🤡", "name": "Payaso / Fail", "category": "humor"},
    {"id": "1f410", "char": "🐐", "name": "GOAT", "category": "humor"},
    {"id": "1f64f", "char": "🙏", "name": "Por favor", "category": "humor"},
    {"id": "1f91d", "char": "🤝", "name": "GG / Respeto", "category": "humor"},
    {"id": "2764", "char": "❤️", "name": "Corazón", "category": "humor"},
    {"id": "1f494", "char": "💔", "name": "Corazón roto", "category": "humor"},
    # Gaming & Competitivo
    {"id": "1f3ae", "char": "🎮", "name": "Control Gaming", "category": "gaming"},
    {"id": "1f3c6", "char": "🏆", "name": "Trofeo", "category": "gaming"},
    {"id": "1f3af", "char": "🎯", "name": "Headshot / Diana", "category": "gaming"},
    {"id": "2694", "char": "⚔️", "name": "Espadas / Duelo", "category": "gaming"},
    {"id": "1f6e1", "char": "🛡️", "name": "Escudo", "category": "gaming"},
    {"id": "1f947", "char": "🥇", "name": "Oro #1", "category": "gaming"},
    {"id": "2705", "char": "✅", "name": "Clutch ganado", "category": "gaming"},
    {"id": "274c", "char": "❌", "name": "Eliminado", "category": "gaming"},
    {"id": "26a0", "char": "⚠️", "name": "Peligro", "category": "gaming"},
    {"id": "1f50a", "char": "🔊", "name": "Volumen alto", "category": "gaming"},
    {"id": "1f4c8", "char": "📈", "name": "Subida de rango", "category": "gaming"},
    {"id": "1f4c9", "char": "📉", "name": "Caída de rango", "category": "gaming"},
    {"id": "1f52b", "char": "🔫", "name": "Disparo", "category": "gaming"},
    {"id": "23f1", "char": "⏱️", "name": "Último segundo", "category": "gaming"},
]

_CATALOG_MAP: Dict[str, Dict[str, str]] = {item["id"]: item for item in EMOJI_CATALOG}


def list_emoji_catalog() -> List[Dict[str, str]]:
    return list(EMOJI_CATALOG)


def _starburst_points(cx: float, cy: float, r_outer: float, r_inner: float, spikes: int) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for i in range(spikes * 2):
        r = r_outer if i % 2 == 0 else r_inner
        ang = (math.pi * i) / spikes - math.pi / 2
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    return pts


def render_supersampled_emoji(norm_id: str, target_path: Path, size: int = 128) -> Path:
    """Render crisp 2x supersampled RGBA emoji icon and downsample with Lanczos."""
    from PIL import Image, ImageDraw

    ss = size * 2
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(ss * 0.08)
    box = [pad, pad, ss - pad, ss - pad]
    mid = ss // 2

    if norm_id == "1f525":  # 🔥 Fire
        outer = [(mid, pad), (int(ss * 0.85), int(ss * 0.48)), (int(ss * 0.77), ss - pad), (int(ss * 0.23), ss - pad), (int(ss * 0.15), int(ss * 0.48))]
        d.polygon(outer, fill="#FF5722", outline="#B71C1C", width=6)
        inner = [(mid, int(ss * 0.30)), (int(ss * 0.70), int(ss * 0.60)), (int(ss * 0.62), ss - pad - 10), (int(ss * 0.38), ss - pad - 10), (int(ss * 0.30), int(ss * 0.60))]
        d.polygon(inner, fill="#FFD400")
        core = [(mid, int(ss * 0.52)), (int(ss * 0.58), int(ss * 0.74)), (mid, ss - pad - 14), (int(ss * 0.42), int(ss * 0.74))]
        d.polygon(core, fill="#FFF9C4")
    elif norm_id == "26a1":  # ⚡ Zap
        pts = [(int(ss * 0.58), pad), (int(ss * 0.20), int(ss * 0.54)), (int(ss * 0.48), int(ss * 0.54)), (int(ss * 0.38), ss - pad), (int(ss * 0.80), int(ss * 0.44)), (int(ss * 0.52), int(ss * 0.44))]
        d.polygon(pts, fill="#FFD400", outline="#CC7A00", width=7)
    elif norm_id == "1f4a5":  # 💥 Collision
        d.polygon(_starburst_points(mid, mid, ss * 0.45, ss * 0.22, 9), fill="#FF3D00", outline="#8E0000", width=5)
        d.polygon(_starburst_points(mid, mid, ss * 0.28, ss * 0.13, 9), fill="#FFD400")
    elif norm_id == "1f4a3":  # 💣 Bomb
        d.ellipse([int(ss * 0.16), int(ss * 0.24), int(ss * 0.82), int(ss * 0.90)], fill="#292F33", outline="#000000", width=6)
        d.line([(int(ss * 0.68), int(ss * 0.28)), (int(ss * 0.84), int(ss * 0.12))], fill="#D7CCC8", width=10)
        d.polygon(_starburst_points(ss * 0.85, ss * 0.12, ss * 0.09, ss * 0.04, 6), fill="#FFD400")
    elif norm_id == "1f480":  # 💀 Skull
        d.ellipse([pad, pad, ss - pad, int(ss * 0.78)], fill="#ECEFF1", outline="#263238", width=8)
        d.rounded_rectangle([int(ss * 0.29), int(ss * 0.60), int(ss * 0.71), ss - pad], radius=16, fill="#ECEFF1", outline="#263238", width=8)
        for sx in (0.26, 0.58):
            d.ellipse([int(ss * sx), int(ss * 0.35), int(ss * (sx + 0.16)), int(ss * 0.52)], fill="#263238")
        d.polygon([(mid, int(ss * 0.52)), (mid - 14, int(ss * 0.64)), (mid + 14, int(ss * 0.64))], fill="#263238")
        for gx in (0.39, 0.50, 0.61):
            d.line([(int(ss * gx), int(ss * 0.74)), (int(ss * gx), ss - pad - 4)], fill="#263238", width=5)
    elif norm_id == "1f451":  # 👑 Crown
        pts = [(pad, int(ss * 0.78)), (pad, int(ss * 0.30)), (int(ss * 0.32), int(ss * 0.54)), (mid, int(ss * 0.22)), (int(ss * 0.68), int(ss * 0.54)), (ss - pad, int(ss * 0.30)), (ss - pad, int(ss * 0.78))]
        d.polygon(pts, fill="#FFD400", outline="#B28900", width=8)
        d.ellipse([mid - 14, int(ss * 0.54), mid + 14, int(ss * 0.68)], fill="#E53935")
    elif norm_id in ("1f3c6", "1f947"):  # 🏆 / 🥇 Trophy & Medal
        d.rounded_rectangle([int(ss * 0.26), int(ss * 0.14), int(ss * 0.74), int(ss * 0.58)], radius=24, fill="#FFD400", outline="#B28900", width=8)
        d.rectangle([int(ss * 0.43), int(ss * 0.58), int(ss * 0.57), int(ss * 0.76)], fill="#FFB300", outline="#B28900", width=6)
        d.rounded_rectangle([int(ss * 0.28), int(ss * 0.76), int(ss * 0.72), int(ss * 0.88)], radius=10, fill="#8D6E63", outline="#4E342E", width=6)
    elif norm_id == "1f3af":  # 🎯 Target / Headshot
        for frac, col in ((0.44, "#E53935"), (0.32, "#FFFFFF"), (0.20, "#E53935"), (0.09, "#FFD400")):
            r = int(ss * frac)
            d.ellipse([mid - r, mid - r, mid + r, mid + r], fill=col, outline="#212121", width=4)
    elif norm_id == "1f3ae":  # 🎮 Gamepad
        d.rounded_rectangle([pad, int(ss * 0.28), ss - pad, int(ss * 0.78)], radius=42, fill="#37474F", outline="#102027", width=8)
        d.line([(int(ss * 0.28), int(ss * 0.44)), (int(ss * 0.28), int(ss * 0.62))], fill="#CFD8DC", width=12)
        d.line([(int(ss * 0.19), int(ss * 0.53)), (int(ss * 0.37), int(ss * 0.53))], fill="#CFD8DC", width=12)
        for bx, by, bc in ((0.68, 0.45, "#39FF14"), (0.77, 0.54, "#FF5252"), (0.59, 0.54, "#40C4FF"), (0.68, 0.63, "#FFD400")):
            d.ellipse([int(ss * bx) - 10, int(ss * by) - 10, int(ss * bx) + 10, int(ss * by) + 10], fill=bc)
    elif norm_id in ("2764", "1f494"):  # ❤️ / 💔 Heart
        d.ellipse([int(ss * 0.12), int(ss * 0.16), int(ss * 0.54), int(ss * 0.56)], fill="#E53935")
        d.ellipse([int(ss * 0.46), int(ss * 0.16), int(ss * 0.88), int(ss * 0.56)], fill="#E53935")
        d.polygon([(int(ss * 0.14), int(ss * 0.42)), (int(ss * 0.86), int(ss * 0.42)), (mid, int(ss * 0.88))], fill="#E53935")
        if norm_id == "1f494":
            d.line([(mid, int(ss * 0.22)), (mid - 16, int(ss * 0.48)), (mid + 14, int(ss * 0.64)), (mid - 6, int(ss * 0.86))], fill="#090A0F", width=12)
    elif norm_id == "2705":  # ✅ Check
        d.rounded_rectangle(box, radius=36, fill="#00C853", outline="#007E33", width=8)
        d.line([(int(ss * 0.25), int(ss * 0.54)), (int(ss * 0.44), int(ss * 0.72)), (int(ss * 0.77), int(ss * 0.32))], fill="#FFFFFF", width=20)
    elif norm_id == "274c":  # ❌ Cross
        d.line([(int(ss * 0.22), int(ss * 0.22)), (int(ss * 0.78), int(ss * 0.78))], fill="#FF1744", width=26)
        d.line([(int(ss * 0.78), int(ss * 0.22)), (int(ss * 0.22), int(ss * 0.78))], fill="#FF1744", width=26)
    elif norm_id == "26a0":  # ⚠️ Warning
        d.polygon([(mid, pad), (ss - pad, ss - pad), (pad, ss - pad)], fill="#FFD400", outline="#212121", width=10)
        d.line([(mid, int(ss * 0.36)), (mid, int(ss * 0.66))], fill="#212121", width=16)
        d.ellipse([mid - 9, int(ss * 0.74), mid + 9, int(ss * 0.83)], fill="#212121")
    elif norm_id == "1f4af":  # 💯 100
        d.rounded_rectangle(box, radius=30, fill="#11131A", outline="#FF1744", width=8)
        d.line([(int(ss * 0.22), int(ss * 0.76)), (int(ss * 0.78), int(ss * 0.72))], fill="#FF1744", width=12)
        d.line([(int(ss * 0.24), int(ss * 0.85)), (int(ss * 0.76), int(ss * 0.81))], fill="#FF1744", width=10)
        d.line([(int(ss * 0.24), int(ss * 0.28)), (int(ss * 0.22), int(ss * 0.62))], fill="#FFD400", width=16)
        d.ellipse([int(ss * 0.34), int(ss * 0.28), int(ss * 0.54), int(ss * 0.62)], outline="#FFD400", width=14)
        d.ellipse([int(ss * 0.60), int(ss * 0.28), int(ss * 0.80), int(ss * 0.62)], outline="#FFD400", width=14)
    elif norm_id == "1f440":  # 👀 Eyes
        for cx_off in (0.31, 0.69):
            cx_i = int(ss * cx_off)
            d.ellipse([cx_i - int(ss * 0.17), int(ss * 0.20), cx_i + int(ss * 0.17), int(ss * 0.80)], fill="#FFFFFF", outline="#263238", width=8)
            d.ellipse([cx_i - int(ss * 0.10), int(ss * 0.38), cx_i - int(ss * 0.10) + int(ss * 0.16), int(ss * 0.64)], fill="#11131A")
    elif norm_id == "1f48e":  # 💎 Diamond
        d.polygon([(int(ss * 0.26), int(ss * 0.18)), (int(ss * 0.74), int(ss * 0.18)), (ss - pad, int(ss * 0.42)), (mid, ss - pad), (pad, int(ss * 0.42))], fill="#00E5FF", outline="#006064", width=8)
        d.line([(pad, int(ss * 0.42)), (ss - pad, int(ss * 0.42))], fill="#E0F7FA", width=6)
    else:
        # Expressive reaction faces (😱, 🤯, 🥶, 🤬, 😤, 😈, 😂, 😭, 🤡, 🫡)
        face_fill = "#FFCC4D"
        outline_col = "#B87700"
        if norm_id == "1f976":
            face_fill, outline_col = "#4FC3F7", "#0277BD"
        elif norm_id == "1f92c":
            face_fill, outline_col = "#FF5252", "#B71C1C"
        elif norm_id == "1f608":
            face_fill, outline_col = "#AB47BC", "#4A148C"
            d.polygon([(int(ss * 0.16), int(ss * 0.26)), (int(ss * 0.08), pad), (int(ss * 0.32), int(ss * 0.16))], fill="#7B1FA2")
            d.polygon([(int(ss * 0.84), int(ss * 0.26)), (int(ss * 0.92), pad), (int(ss * 0.68), int(ss * 0.16))], fill="#7B1FA2")
        elif norm_id == "1f921":
            face_fill, outline_col = "#FAFAFA", "#B0BEC5"

        d.ellipse(box, fill=face_fill, outline=outline_col, width=8)
        if norm_id == "1f92f":  # 🤯 Exploding crown
            d.polygon(_starburst_points(mid, ss * 0.18, ss * 0.28, ss * 0.14, 7), fill="#FF6D00", outline="#BF360C", width=5)

        # Eyes
        d.ellipse([int(ss * 0.27), int(ss * 0.34), int(ss * 0.41), int(ss * 0.49)], fill="#263238")
        d.ellipse([int(ss * 0.59), int(ss * 0.34), int(ss * 0.73), int(ss * 0.49)], fill="#263238")

        if norm_id == "1f921":  # 🤡 Red clown nose
            d.ellipse([mid - 18, mid - 12, mid + 18, mid + 22], fill="#FF1744")

        if norm_id in ("1f631", "1f92f"):  # 😱 / 🤯 Shock mouth
            d.ellipse([int(ss * 0.38), int(ss * 0.56), int(ss * 0.62), int(ss * 0.84)], fill="#4E342E")
        elif norm_id in ("1f602", "1f62d"):  # 😂 / 😭 Tears
            d.arc([int(ss * 0.28), int(ss * 0.52), int(ss * 0.72), int(ss * 0.82)], start=0, end=180, fill="#4E342E", width=12)
            d.ellipse([int(ss * 0.12), int(ss * 0.48), int(ss * 0.26), int(ss * 0.74)], fill="#29B6F6")
            d.ellipse([int(ss * 0.74), int(ss * 0.48), int(ss * 0.88), int(ss * 0.74)], fill="#29B6F6")
        elif norm_id == "1f976":  # 🥶 Chattering teeth
            d.rounded_rectangle([int(ss * 0.28), int(ss * 0.62), int(ss * 0.72), int(ss * 0.78)], radius=10, fill="#FFFFFF", outline="#01579B", width=6)
        elif norm_id == "1f92c":  # 🤬 Censor bar
            d.rectangle([int(ss * 0.24), int(ss * 0.60), int(ss * 0.76), int(ss * 0.78)], fill="#11131A")
        else:
            d.arc([int(ss * 0.28), int(ss * 0.48), int(ss * 0.72), int(ss * 0.80)], start=12, end=168, fill="#4E342E", width=12)

    final_img = img.resize((size, size), resample=Image.Resampling.LANCZOS)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(target_path, format="PNG")
    return target_path
