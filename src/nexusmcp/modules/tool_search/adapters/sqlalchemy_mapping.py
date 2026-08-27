"""Tool Search Embedding Domain 与 ORM Model 显式映射。"""

from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import ToolSearchEmbeddingModel
from nexusmcp.modules.tool_search.domain import EmbeddingVector, ToolSearchEmbedding


def embedding_from_model(model: ToolSearchEmbeddingModel) -> ToolSearchEmbedding:
    values = tuple(float(value) for value in model.embedding)
    return ToolSearchEmbedding(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        tool_version_id=str(model.tool_version_id),
        embedding_model=model.embedding_model,
        embedding_dimensions=model.embedding_dimensions,
        source_digest=model.source_digest,
        vector=EmbeddingVector(
            model=model.embedding_model,
            dimensions=model.embedding_dimensions,
            values=values,
        ),
        indexed_at=model.indexed_at,
    )
