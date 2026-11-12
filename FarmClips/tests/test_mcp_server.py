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


def test_mcp_list_clips_and_sessions():
    from clipsserver.mcp.server import _api_get

    with patch("clipsserver.mcp.server._api_get") as mock_get:
        mock_get.side_effect = lambda ep: (
            [{"id": "ses_1", "title": "Test Ses", "state": "DELIVERED", "clips_count": 3, "rendered_count": 2}]
            if ep == "/sessions"
            else [
                {"id": "clip_1", "start": 10.0, "end": 25.0, "final_score": 90.0, "has_final": True, "has_draft": False, "post_title": "Clip 1"}
            ]
            if ep == "/sessions/ses_1/clips"
            else []
        )
        server = create_mcp_server()
        # Find tools
        list_sess_tool = server._tool_manager.get_tool("list_sessions")
        list_clips_tool = server._tool_manager.get_tool("list_clips")

        sess_res = json.loads(list_sess_tool.fn())
        assert len(sess_res) == 1
        assert sess_res[0]["clips_count"] == 3

        clips_res = json.loads(list_clips_tool.fn(session_id="ses_1"))
        assert len(clips_res) == 1
        assert clips_res[0]["clip_id"] == "clip_1"
        assert clips_res[0]["duration_s"] == 15.0
        assert clips_res[0]["has_final_render"] is True
