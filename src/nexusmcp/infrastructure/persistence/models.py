"""集中导入 ORM Model，确保 Alembic 能发现完整 Metadata。"""

from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.audit.adapters.sqlalchemy_models import AuditEventModel
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.execution.adapters.sqlalchemy_models import (
    ExecutionAttemptModel,
    ToolExecutionModel,
)
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_models import (
    ImportedOperationModel,
    OpenApiImportJobModel,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import (
    ToolSearchEmbeddingModel,
    ToolSearchReindexJobModel,
)

ALL_MODELS = (
    TenantModel,
    UpstreamServiceModel,
    OpenApiImportJobModel,
    ImportedOperationModel,
    ToolModel,
    ToolVersionModel,
    ToolSearchEmbeddingModel,
    ToolSearchReindexJobModel,
    ToolBindingModel,
    ApprovalRequestModel,
    ToolExecutionModel,
    ExecutionAttemptModel,
    AuditEventModel,
)

__all__ = ["ALL_MODELS"]
