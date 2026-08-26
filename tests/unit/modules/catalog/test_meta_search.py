"""Meta Tool Search 的模式、Over-fetch 与 Policy Filter 测试。"""

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.catalog.meta_search import (
    SearchTools,
    SearchToolsQuery,
    ToolRetrievalMode,
)
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.policy.domain import PolicyDecision, PolicyEffect, PolicyEvaluationInput
from nexusmcp.shared.errors import ToolSearchModeUnavailableError
from nexusmcp.shared.request_context import ProtocolEra, RequestContext


class SelectivePolicyEvaluator:
    async def evaluate(self, policy_input: PolicyEvaluationInput) -> PolicyDecision:
        allowed = policy_input.tool_id == "tool-get"
        return PolicyDecision(
            effect=PolicyEffect.ALLOW if allowed else PolicyEffect.DENY,
            policy_version="policy-v1",
            reason_code="allowed" if allowed else "denied",
        )


def published_tool(
    tool_id: str,
    name: str,
    side_effect: ToolSideEffect,
) -> PublishedTool:
    return PublishedTool(
        tool_id=tool_id,
        tool_version_id=f"{tool_id}-v1",
        tenant_id="tenant-a",
        canonical_name=name,
        display_name=name.replace(".", " ").title(),
        description="Inventory warehouse tool.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.AUTHENTICATED,
        side_effect=side_effect,
        schema_digest="1" * 64,
        owner="inventory-platform",
        tags=("inventory", "warehouse"),
    )


def context() -> RequestContext:
    return RequestContext(
        request_id="request-meta-search",
        trace_id="a" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id="tenant-a",
        principal_id="operator",
        authn_method="test",
    )


def use_case() -> SearchTools:
    repository = InMemoryToolCatalogRepository(
        published_tools=[
            published_tool("tool-get", "inventory.get_status", ToolSideEffect.READ_ONLY),
            published_tool(
                "tool-reserve",
                "inventory.reserve_stock",
                ToolSideEffect.NON_IDEMPOTENT_WRITE,
            ),
        ]
    )
    return SearchTools(
        lexical_search=SearchPublishedTools(repository),
        principal_resolver=ContextPrincipalResolver(),
        policy_evaluator=SelectivePolicyEvaluator(),
    )


@pytest.mark.asyncio
async def test_lexical_search_filters_denied_candidates_after_overfetch() -> None:
    hits = await use_case().execute(
        SearchToolsQuery(
            context=context(),
            text="inventory",
            retrieval_mode=ToolRetrievalMode.LEXICAL,
            limit=5,
            namespace="inventory",
        )
    )

    assert [hit.tool.canonical_name for hit in hits] == ["inventory.get_status"]


@pytest.mark.asyncio
async def test_hybrid_mode_is_stable_but_unavailable_before_vector_index() -> None:
    with pytest.raises(ToolSearchModeUnavailableError):
        await use_case().execute(
            SearchToolsQuery(
                context=context(),
                text="things are almost sold out",
                retrieval_mode=ToolRetrievalMode.HYBRID,
            )
        )
