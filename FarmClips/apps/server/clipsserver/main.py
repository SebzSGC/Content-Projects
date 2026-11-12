"""CLI entrypoint for ClipsApp server (`clipsserver serve`, `clipsserver codegen`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import create_app
from .config import get_server_settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="clipsserver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="Inicia el servidor híbrido único (API + Orquestador + 3 Pools)")

    p_cg = sub.add_parser("codegen", help="Exporta JSON Schema de EditPlan v2, OpenAPI y tipos TypeScript")
    p_cg.add_argument("--web-dir", type=Path, default=Path("apps/web"))

    sub.add_parser("mcp-config", help="Genera la configuración para Claude Desktop (FarmClips + FilmCraft MCP)")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        cfg = get_server_settings()
        uvicorn.run(
            "clipsserver.main:asgi_app",
            factory=True,
            host=cfg.host,
            port=cfg.port,
            reload=False,
        )
        return 0

    if args.cmd == "codegen":
        from clipseditplan import export_json_schema, generate_typescript

        schema_file = export_json_schema()
        ts_file = generate_typescript(args.web_dir / "src" / "lib" / "api" / "editplan.ts")
        app = create_app(use_process_pool=False, enable_drive_watcher=False)
        try:
            openapi_path = args.web_dir / "src" / "lib" / "api" / "openapi.json"
            openapi_path.parent.mkdir(parents=True, exist_ok=True)
            openapi_path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            app.state.orchestrator.db.close()
        print(f"Exported EditPlan schema -> {schema_file}")
        print(f"Generated TypeScript EditPlan -> {ts_file}")
        print(f"Exported OpenAPI contract -> {openapi_path}")
        return 0

    if args.cmd == "mcp-config":
        import sys
        from .filmcraft import FilmCraftLauncher

        launcher = FilmCraftLauncher()
        cli_path = launcher.find_cli_binary()

        config = {
            "mcpServers": {
                "farmclips": {
                    "command": sys.executable,
                    "args": ["-m", "clipsserver.mcp"],
                    "env": {"FARMCLIPS_API": "http://127.0.0.1:8790"},
                }
            }
        }

        if cli_path:
            config["mcpServers"]["filmcraft"] = {
                "command": str(cli_path),
                "args": ["mcp", "--bridge", f"127.0.0.1:{launcher.bridge_port}"],
            }

        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0

    return 1


def asgi_app():
    return create_app()


if __name__ == "__main__":
    raise SystemExit(main())
