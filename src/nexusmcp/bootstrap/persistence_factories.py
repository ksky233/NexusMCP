"""在 Use Case 执行时才从 DatabaseRuntime 获取 Session Factory。"""

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.approval.adapters.sqlalchemy_uow import SqlAlchemyApprovalUnitOfWork
from nexusmcp.modules.catalog.adapters.sqlalchemy_uow import SqlAlchemyCatalogUnitOfWork
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_review_uow import (
    SqlAlchemyReviewUnitOfWork,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_uow import (
    SqlAlchemyOpenApiImportUnitOfWork,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_uow import SqlAlchemyRegistryUnitOfWork


class RuntimeCatalogUnitOfWorkFactory:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    def __call__(self) -> SqlAlchemyCatalogUnitOfWork:
        return SqlAlchemyCatalogUnitOfWork(self._database_runtime.require_session_factory())


class RuntimeApprovalUnitOfWorkFactory:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    def __call__(self) -> SqlAlchemyApprovalUnitOfWork:
        return SqlAlchemyApprovalUnitOfWork(self._database_runtime.require_session_factory())


class RuntimeOpenApiImportUnitOfWorkFactory:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    def __call__(self) -> SqlAlchemyOpenApiImportUnitOfWork:
        return SqlAlchemyOpenApiImportUnitOfWork(self._database_runtime.require_session_factory())


class RuntimeReviewUnitOfWorkFactory:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    def __call__(self) -> SqlAlchemyReviewUnitOfWork:
        return SqlAlchemyReviewUnitOfWork(self._database_runtime.require_session_factory())


class RuntimeRegistryUnitOfWorkFactory:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    def __call__(self) -> SqlAlchemyRegistryUnitOfWork:
        return SqlAlchemyRegistryUnitOfWork(self._database_runtime.require_session_factory())
