"""内建 Meta Tool 使用的 Lexical/Hybrid Tool Search 编排。"""

from dataclasses import dataclass
from enum import StrEnum

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit, ToolSideEffect
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.identity.ports import PrincipalResolver
from nexusmcp.modules.policy.domain import PolicyEffect, PolicyEvaluationInput, ToolAction
from nexusmcp.modules.policy.ports import PolicyEvaluator
from nexusmcp.shared.digests import canonical_json_digest
from nexusmcp.shared.errors import InvalidArgumentsError, ToolSearchModeUnavailableError
from nexusmcp.shared.request_context import RequestContext


class ToolRetrievalMode(StrEnum):
    LEXICAL = "lexical"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class SearchToolsQuery:
    context: RequestContext
    text: str
    retrieval_mode: ToolRetrievalMode
    limit: int = 5
    namespace: str | None = None
    side_effect: ToolSideEffect | None = None


class SearchTools:
    def __init__(
        self,
        *,
        lexical_search: SearchPublishedTools,
        principal_resolver: PrincipalResolver,
        policy_evaluator: PolicyEvaluator,
        hybrid_search: SearchPublishedTools | None = None,
        overfetch_factor: int = 4,
    ) -> None:
        if overfetch_factor <= 0:
            raise ValueError("tool search overfetch factor must be positive")
        self._lexical_search = lexical_search
        self._hybrid_search = hybrid_search
        self._principal_resolver = principal_resolver
        self._policy_evaluator = policy_evaluator
        self._overfetch_factor = overfetch_factor

    async def execute(self, query: SearchToolsQuery) -> tuple[PublishedToolSearchHit, ...]:
        if not 1 <= query.limit <= 10:
            raise InvalidArgumentsError("Meta Tool search limit must be between 1 and 10")
        if query.retrieval_mode is ToolRetrievalMode.HYBRID:
            if self._hybrid_search is None:
                raise ToolSearchModeUnavailableError("hybrid tool search is not indexed")
            search = self._hybrid_search
        else:
            search = self._lexical_search
        raw_hits = await search.execute(
            SearchPublishedToolsQuery(
                context=query.context,
                text=query.text,
                limit=min(query.limit * self._overfetch_factor, 50),
                namespace=query.namespace,
                side_effect=query.side_effect,
            )
        )
        principal = await self._principal_resolver.resolve(query.context)
        visible: list[PublishedToolSearchHit] = []
        empty_arguments_digest = canonical_json_digest({})
        for hit in raw_hits:
            decision = await self._policy_evaluator.evaluate(
                PolicyEvaluationInput(
                    tenant_id=query.context.tenant_id,
                    principal=principal,
                    tool_id=hit.tool.tool_id,
                    tool_version_id=hit.tool.tool_version_id,
                    action=ToolAction.CALL,
                    side_effect=hit.tool.side_effect,
                    arguments_digest=empty_arguments_digest,
                )
            )
            if decision.effect is not PolicyEffect.DENY:
                visible.append(hit)
            if len(visible) == query.limit:
                break
        return tuple(visible)
