"""Command line: ``gameclips serve`` starts the API; the rest run one pipeline
step in the foreground (handy for testing without the UI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import get_settings
from .domain import SessionSpec, SourceMode, new_id, to_dict


def _print_progress(stage: str, progress: float, message: str) -> None:
    print(f"\r[{progress * 100:5.1f}%] {stage:<14} {message[:70]:<70}", end="", file=sys.stderr, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gameclips")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="Inicia la API HTTP")

    p = sub.add_parser("analyze", help="Crea una sesión (modo split) y la analiza")
    p.add_argument("--gameplay", required=True, help="Video del juego con el audio mezclado")
    p.add_argument("--camera", required=True, help="Video de la cámara")
    p.add_argument("--title", default="")
    p.add_argument("--language", default="es")
    p.add_argument("--voiceprint")

    p = sub.add_parser("render", help="Renderiza un candidato")
    p.add_argument("session_id")
    p.add_argument("candidate_id")
    p.add_argument("--captions", choices=["streamer", "all", "none"], default="streamer")

    p = sub.add_parser("enroll", help="Registra la voz del streamer")
    p.add_argument("name")
    p.add_argument("audio", type=Path)

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        s = get_settings()
        uvicorn.run("gameclips.api:app", host=s.host, port=s.port, reload=False)
        return 0

    from . import pipeline
    from .storage import SessionStore

    if args.cmd == "analyze":
        spec = SessionSpec(
            id=new_id("ses"),
            mode=SourceMode.SPLIT,
            title=args.title,
            gameplay_path=str(Path(args.gameplay).resolve()),
            camera_path=str(Path(args.camera).resolve()),
            language=args.language,
            voiceprint=args.voiceprint,
        )
        SessionStore(spec.id).ensure().save("session.json", spec)
        pipeline.ingest(spec.id, _print_progress)
        pipeline.analyze(spec.id, _print_progress)
        print(file=sys.stderr)
        print(json.dumps({"session_id": spec.id, "candidates": to_dict(SessionStore(spec.id).candidates())}, ensure_ascii=False, indent=1))
        return 0

    if args.cmd == "render":
        from .domain import RenderOptions

        result = pipeline.render(args.session_id, args.candidate_id, _print_progress, RenderOptions(captions=args.captions))
        print(file=sys.stderr)
        print(json.dumps(result))
        return 0

    if args.cmd == "enroll":
        from .audio.voiceprint import enroll

        print(enroll(args.name, args.audio))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
