"""显式运维命令入口；不会在 Import 时启动 ASGI App。"""

import argparse
import asyncio
import sys
import uuid

import httpx

from nexusmcp.bootstrap.config import Settings
from nexusmcp.bootstrap.persistence_factories import RuntimeToolSearchUnitOfWorkFactory
from nexusmcp.infrastructure.clock import SystemClock
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.tool_search.adapters.siliconflow import SiliconFlowEmbeddingProvider
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.reindex_tools import (
    ReindexTools,
    ReindexToolsCommand,
    ReindexToolsResult,
)
from nexusmcp.shared.errors import NexusMcpError
from nexusmcp.shared.request_context import ActorContext


def main() -> None:
    parser = argparse.ArgumentParser(prog="nexusmcp")
    commands = parser.add_subparsers(dest="command", required=True)
    reindex = commands.add_parser(
        "reindex-tools",
        help="Build missing or stale Tool Search Embedding projections.",
    )
    reindex.add_argument("--tenant-id")
    reindex.add_argument("--batch-size", type=int)
    reindex.add_argument("--force", action="store_true")
    reindex.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    if arguments.command != "reindex-tools":  # pragma: no cover - argparse 已限制
        parser.error("unsupported command")
    try:
        result = asyncio.run(_run_reindex(arguments))
    except NexusMcpError as error:
        print(f"error: {error.code}: {error.safe_message}", file=sys.stderr)
        raise SystemExit(2) from None
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    _print_result(result)


async def _run_reindex(arguments: argparse.Namespace) -> ReindexToolsResult:
    settings = Settings()
    database_url = settings.database_url
    if settings.catalog_backend != "postgresql" or database_url is None:
        raise RuntimeError("reindex-tools requires PostgreSQL catalog configuration")
    tenant_id = arguments.tenant_id or settings.local_tenant_id
    batch_size = arguments.batch_size or settings.embedding_batch_size
    runtime = DatabaseRuntime(
        database_url.get_secret_value(),
        echo=settings.database_echo,
        readiness_timeout_seconds=settings.database_readiness_timeout_seconds,
    )
    client: httpx.AsyncClient | None = None
    try:
        await runtime.start()
        provider = None
        if not arguments.dry_run:
            api_key = settings.embedding_api_key
            if api_key is None:
                raise RuntimeError("NEXUSMCP_EMBEDDING_API_KEY is required")
            client = httpx.AsyncClient(trust_env=False)
            provider = SiliconFlowEmbeddingProvider(
                client,
                api_url=settings.embedding_api_url,
                api_key=SecretValue(api_key.get_secret_value()),
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                timeout_seconds=settings.embedding_timeout_seconds,
                max_batch_size=settings.embedding_batch_size,
            )
        use_case = ReindexTools(
            published_tools=SqlAlchemyPublishedToolReader(runtime),
            unit_of_work_factory=RuntimeToolSearchUnitOfWorkFactory(runtime),
            document_builder=ToolSearchDocumentBuilder(),
            embedding_provider=provider,
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
            clock=SystemClock(),
            identifier_generator=UuidIdentifierGenerator(),
        )
        return await use_case.execute(
            ReindexToolsCommand(
                context=ActorContext(
                    request_id=str(uuid.uuid4()),
                    trace_id=uuid.uuid4().hex,
                    tenant_id=tenant_id,
                    principal_id=settings.local_admin_principal_id,
                    authn_method="local_cli",
                ),
                batch_size=batch_size,
                force=arguments.force,
                dry_run=arguments.dry_run,
            )
        )
    finally:
        if client is not None:
            await client.aclose()
        if runtime.is_started:
            await runtime.stop()


def _print_result(result: ReindexToolsResult) -> None:
    print(f"Published Tools: {result.published_count}")
    print(f"Already Current: {result.current_count}")
    print(f"Pending: {result.pending_count}")
    print(f"Embedded: {result.embedded_count}")
    print(f"Batches: {result.batch_count}")
    print(f"Model: {result.model}")
    print(f"Dimensions: {result.dimensions}")
    print(f"Dry Run: {str(result.dry_run).lower()}")
