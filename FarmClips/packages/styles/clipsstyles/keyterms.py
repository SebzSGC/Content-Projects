"""Automatic per-game keyterm profiles for Deepgram Nova-3 & Groq Whisper boosting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

KEYTERMS_DIR = Path(__file__).resolve().parent / "keyterms"

GENERAL_GAMING_ES: List[str] = [
    "clutch",
    "headshot",
    "one tap",
    "ace",
    "ulti",
    "nerfeo",
    "tryhard",
    "rushear",
    "tilteado",
    "campero",
    "no puede ser",
    "ronda final",
]

BUILTIN_GAME_PROFILES: Dict[str, Dict[str, Any]] = {
    "valorant": {
        "name": "Valorant",
        "triggers": ["valorant", "valo", "radiante", "inmortal", "vandal", "jett", "reyna"],
        "keyterms": [
            "Valorant", "Jett", "Reyna", "Raze", "Omen", "Sova", "Chamber", "Clove", "Cypher", "Killjoy",
            "Vandal", "Phantom", "Operator", "Sheriff", "Spike", "Radiante", "Inmortal", "Ascendente",
            "defuse", "retake", "eco", "one tap", "clutch", "ace",
        ],
    },
    "lol": {
        "name": "League of Legends",
        "triggers": ["lol", "league of legends", "grieta", "baron", "pentakill", "clasificatoria"],
        "keyterms": [
            "League of Legends", "Baron Nashor", "Dragón Ancestral", "Heraldo", "pentakill", "quadrakill",
            "flash", "smite", "jungla", "botlane", "toplane", "midlane", "gankeo", "inhibidor", "nexo",
            "Challenger", "Maestro", "Diamante", "teamfight", "outplay",
        ],
    },
    "fortnite": {
        "name": "Fortnite",
        "triggers": ["fortnite", "victoria magistral", "boxfight", "zero build", "tormenta"],
        "keyterms": [
            "Fortnite", "Victoria Magistral", "tormenta", "escuadrón", "boxfight", "editar", "construir",
            "escopeta", "escudo", "minis", "reboot", "drop", "zone wars", "Unreal", "clutch",
        ],
    },
    "cs2": {
        "name": "Counter-Strike 2",
        "triggers": ["cs2", "counter-strike", "counter strike", "csgo", "faceit", "mirage", "inferno"],
        "keyterms": [
            "Counter-Strike", "CS2", "Faceit", "AWP", "AK-47", "Deagle", "Mirage", "Inferno", "Dust2",
            "Nuke", "Anubis", "Ancient", "molotov", "flashbang", "humo", "defuse", "clutch", "ace", "eco",
        ],
    },
    "minecraft": {
        "name": "Minecraft",
        "triggers": ["minecraft", "hardcore", "nether", "creeper", "speedrun", "uhc"],
        "keyterms": [
            "Minecraft", "Creeper", "Enderman", "Nether", "Ender Dragon", "Wither", "diamante",
            "netherita", "totem", "water drop", "hardcore", "speedrun", "bastión", "elytra", "aldeano",
        ],
    },
    "warzone": {
        "name": "Call of Duty: Warzone",
        "triggers": ["warzone", "cod", "gulag", "resurgimiento", "rebirth"],
        "keyterms": [
            "Warzone", "Gulag", "loadout", "UAV", "placas", "gas", "francotirador", "resurgimiento",
            "contrato", "abatido", "rematar", "escuadrón", "victoria", "clutch",
        ],
    },
    "gta": {
        "name": "GTA V / Roleplay",
        "triggers": ["gta", "roleplay", "gtarp", "los santos", "atraco"],
        "keyterms": [
            "GTA", "Roleplay", "Los Santos", "comisaría", "persecución", "atraco", "secuestro",
            "federales", "banda", "helicóptero", "código", "radio",
        ],
    },
    "ea_fc": {
        "name": "EA Sports FC",
        "triggers": ["eafc", "ea fc", "fifa", "fut", "champions", "ultimate team"],
        "keyterms": [
            "EA FC", "Ultimate Team", "FUT Champions", "Rivals", "caminante", "icono", "Mbappé",
            "Vinicius", "Bellingham", "golazo", "escuadra", "penalti", "contraataque", "remontada",
        ],
    },
}


def load_all_game_profiles() -> Dict[str, Dict[str, Any]]:
    profiles = {k: dict(v) for k, v in BUILTIN_GAME_PROFILES.items()}
    if KEYTERMS_DIR.is_dir():
        for jf in sorted(KEYTERMS_DIR.glob("*.json")):
            try:
                raw = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("keyterms"):
                    profiles[jf.stem.lower()] = raw
            except Exception:
                continue
    return profiles


def list_game_profiles() -> List[Dict[str, Any]]:
    profiles = load_all_game_profiles()
    return [
        {
            "id": gid,
            "name": p.get("name", gid),
            "triggers": p.get("triggers", []),
            "keyterms_count": len(p.get("keyterms", [])),
            "sample_keyterms": list(p.get("keyterms", []))[:8],
        }
        for gid, p in sorted(profiles.items())
    ]


def resolve_game_keyterms(
    title: str = "",
    recording_name: str = "",
    base_keyterms: Sequence[str] = (),
    max_terms: int = 50,
) -> Tuple[Optional[str], List[str]]:
    """Auto-detect game from session title / folder name and return (game_id, deduplicated_keyterms[:50])."""
    haystack = f"{title} {recording_name}".lower().replace("_", " ").replace("-", " ")
    profiles = load_all_game_profiles()

    detected_game: Optional[str] = None
    game_terms: List[str] = []
    for gid, prof in profiles.items():
        triggers = [str(t).lower() for t in prof.get("triggers", [gid])]
        if any(tr in haystack for tr in triggers):
            detected_game = gid
            game_terms = [str(k).strip() for k in prof.get("keyterms", []) if str(k).strip()]
            break

    # Priority order: game-specific terms -> significant title tokens -> user base keyterms -> general ES gaming slang
    merged: List[str] = []
    seen_low = set()

    def _add_many(items: Sequence[str]) -> None:
        for item in items:
            clean = item.strip()
            if not clean or len(clean) < 2:
                continue
            low = clean.lower()
            if low not in seen_low:
                seen_low.add(low)
                merged.append(clean)

    _add_many(game_terms)
    title_words = [
        w.strip(".,!¡¿?()[]{}")
        for w in f"{title} {recording_name}".replace("_", " ").replace("-", " ").split()
        if len(w.strip(".,!¡¿?()[]{}")) >= 4 and not w.isdigit()
    ]
    _add_many(title_words[:8])
    _add_many(base_keyterms)
    _add_many(GENERAL_GAMING_ES)

    return detected_game, merged[:max_terms]
