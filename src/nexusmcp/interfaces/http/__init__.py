"""HTTP 入站 Adapter 的共享错误边界。"""

from nexusmcp.interfaces.http.errors import register_http_exception_handlers

__all__ = ["register_http_exception_handlers"]
