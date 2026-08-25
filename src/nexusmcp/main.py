"""ASGI 部署入口。"""

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import get_settings
from nexusmcp.infrastructure.observability import configure_logging

settings = get_settings()
configure_logging(
    service=settings.service_name,
    environment=settings.environment,
    level=settings.log_level,
    log_format=settings.log_format,
)
app = create_app(settings)
