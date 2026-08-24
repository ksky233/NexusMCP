"""ASGI 部署入口。"""

from nexusmcp.bootstrap.app import create_app

app = create_app()
