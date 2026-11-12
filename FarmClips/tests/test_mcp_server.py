"""Pruebas unitarias para el servidor MCP de FarmClips."""

import json
from io import StringIO
from unittest.mock import patch

from clipsserver.main import main
from clipsserver.mcp.server import create_mcp_server


def test_mcp_server_tools_registered():
    server = create_mcp_server()
    # En mcp 2.x, _tool_manager.list_tools() lista las herramientas
    tools = server._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    expected = [
        "list_sessions",
        "list_clips",
        "get_clip",
        "get_transcript",
        "update_editplan",
        "export_to_filmcraft",
        "open_in_filmcraft",
        "render_clip",
        "get_render_status",
    ]
    for exp in expected:
        assert exp in tool_names, f"Falta la herramienta {exp} en el servidor MCP"


def test_mcp_config_cli():
    with patch("sys.stdout", new_callable=StringIO) as mock_out:
        ret = main(["mcp-config"])
        assert ret == 0
        output = mock_out.getvalue()
        config = json.loads(output)
        assert "mcpServers" in config
        assert "farmclips" in config["mcpServers"]
        assert "filmcraft" in config["mcpServers"]
        assert config["mcpServers"]["farmclips"]["args"] == ["-m", "clipsserver.mcp"]
