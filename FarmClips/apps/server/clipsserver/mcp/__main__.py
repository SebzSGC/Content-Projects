"""Punto de entrada ejecutable para el servidor stdio de farmclips-mcp."""

from .server import create_mcp_server

def main():
    server = create_mcp_server()
    server.run(transport="stdio")

if __name__ == "__main__":
    main()
