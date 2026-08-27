"""Published Tool 到 Embedding Projection 的幂等 Reindex Use Case。"""

from dataclasses import dataclass

from nexusmcp.modules.catalog.ports import PublishedToolReader
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.domain import ToolSearchDocument, ToolSearchEmbedding
from nexusmcp.modules.tool_search.ports import (
    EmbeddingProvider,
    ToolSearchUnitOfWorkFactory,
)
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import EmbeddingResponseError, EmbeddingUnavailableError
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class ReindexToolsCommand:
    context: ActorContext
    batch_size: int = 16
    force: bool = False
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class ReindexToolsResult:
    published_count: int
    current_count: int
    pending_count: int
    embedded_count: int
    batch_count: int
    model: str
    dimensions: int
    dry_run: bool


class ReindexTools:
    def __init__(
        self,
        *,
        published_tools: PublishedToolReader,
        unit_of_work_factory: ToolSearchUnitOfWorkFactory,
        document_builder: ToolSearchDocumentBuilder,
        embedding_provider: EmbeddingProvider | None,
        embedding_model: str,
        embedding_dimensions: int,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._published_tools = published_tools
        self._unit_of_work_factory = unit_of_work_factory
        self._document_builder = document_builder
        self._embedding_provider = embedding_provider
        if not embedding_model.strip() or embedding_dimensions <= 0:
            raise ValueError("reindex embedding configuration was invalid")
        if embedding_provider is not None and (
            embedding_provider.model != embedding_model
            or embedding_provider.dimensions != embedding_dimensions
        ):
            raise ValueError("embedding provider did not match reindex configuration")
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._clock = clock
        self._identifier_generator = identifier_generator

    async def execute(self, command: ReindexToolsCommand) -> ReindexToolsResult:
        if not 1 <= command.batch_size <= 64:
            raise ValueError("reindex batch size must be between 1 and 64")
        tools = await self._published_tools.list_published_by_tenant(command.context.tenant_id)
        documents = tuple(
            self._document_builder.build(tool)
            for tool in sorted(tools, key=lambda item: item.canonical_name)
        )
        existing = await self._load_existing(
            command.context.tenant_id,
            documents,
        )
        pending = tuple(
            document
            for document in documents
            if command.force
            or document.tool_version_id not in existing
            or existing[document.tool_version_id].source_digest != document.source_digest
        )
        current_count = len(documents) - len(pending)
        if command.dry_run or not pending:
            return ReindexToolsResult(
                published_count=len(documents),
                current_count=current_count,
                pending_count=len(pending),
                embedded_count=0,
                batch_count=0,
                model=self._embedding_model,
                dimensions=self._embedding_dimensions,
                dry_run=command.dry_run,
            )

        provider = self._embedding_provider
        if provider is None:
            raise EmbeddingUnavailableError("embedding provider was not configured")
        batch_count = 0
        embedded_count = 0
        for start in range(0, len(pending), command.batch_size):
            batch = pending[start : start + command.batch_size]
            vectors = await provider.embed(tuple(document.content for document in batch))
            if len(vectors) != len(batch):
                raise EmbeddingResponseError("embedding provider violated batch count contract")
            projections = tuple(
                ToolSearchEmbedding(
                    id=(
                        existing[document.tool_version_id].id
                        if document.tool_version_id in existing
                        else self._identifier_generator.new_id()
                    ),
                    tenant_id=document.tenant_id,
                    tool_version_id=document.tool_version_id,
                    embedding_model=self._embedding_model,
                    embedding_dimensions=self._embedding_dimensions,
                    source_digest=document.source_digest,
                    vector=vector,
                    indexed_at=self._clock.now(),
                )
                for document, vector in zip(batch, vectors, strict=True)
            )
            async with self._unit_of_work_factory() as unit_of_work:
                await unit_of_work.embeddings.upsert_many(
                    command.context.tenant_id,
                    projections,
                )
                await unit_of_work.commit()
            batch_count += 1
            embedded_count += len(batch)
        return ReindexToolsResult(
            published_count=len(documents),
            current_count=current_count,
            pending_count=len(pending),
            embedded_count=embedded_count,
            batch_count=batch_count,
            model=self._embedding_model,
            dimensions=self._embedding_dimensions,
            dry_run=False,
        )

    async def _load_existing(
        self,
        tenant_id: str,
        documents: tuple[ToolSearchDocument, ...],
    ) -> dict[str, ToolSearchEmbedding]:
        async with self._unit_of_work_factory() as unit_of_work:
            embeddings = await unit_of_work.embeddings.list_by_tool_versions(
                tenant_id,
                tuple(document.tool_version_id for document in documents),
                embedding_model=self._embedding_model,
                embedding_dimensions=self._embedding_dimensions,
            )
        return {embedding.tool_version_id: embedding for embedding in embeddings}
