"""三个企业场景 Fake API 的单进程部署入口。"""

from fastapi import FastAPI

from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from examples.upstream_apis.inventory.app import app as inventory_app
from examples.upstream_apis.operations.app import app as operations_app

app = FastAPI(
    title="NexusMCP Demo Upstreams",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    return {"status": "ok"}


# 子应用保留自己的路由和 OpenAPI 行为，部署时只增加稳定的场景前缀。
app.mount("/employee-directory", employee_directory_app)
app.mount("/operations", operations_app)
app.mount("/inventory", inventory_app)
