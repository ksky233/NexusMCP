"""Reciprocal Rank Fusion 的排名、去重与稳定 Tie-break 测试。"""

import pytest

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    PublishedToolSearchHit,
    ToolSideEffect,
    ToolVisibility,
)
from nexusmcp.modules.tool_search.rank_fusion import ReciprocalRankFusion


def hit(name: str, raw_score: float) -> PublishedToolSearchHit:
    identity = name.replace(".", "-")
    return PublishedToolSearchHit(
        tool=PublishedTool(
            tool_id=identity,
            tool_version_id=f"{identity}-v1",
            tenant_id="tenant-a",
            canonical_name=name,
            display_name=name,
            description="Tool for rank fusion test.",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            version=1,
            visibility=ToolVisibility.PUBLIC,
            side_effect=ToolSideEffect.READ_ONLY,
            schema_digest="1" * 64,
        ),
        rank=raw_score,
    )


def test_rrf_uses_positions_instead_of_incompatible_raw_scores() -> None:
    lexical = (hit("inventory.alpha", 1000.0), hit("inventory.beta", 0.01))
    vector = (hit("inventory.beta", -100.0), hit("inventory.gamma", 9999.0))

    fused = ReciprocalRankFusion(rank_constant=60).fuse(
        (lexical, vector),
        limit=3,
    )

    assert [item.tool.canonical_name for item in fused] == [
        "inventory.beta",
        "inventory.alpha",
        "inventory.gamma",
    ]
    assert fused[0].rank == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1].rank == pytest.approx(1 / 61)
    assert fused[2].rank == pytest.approx(1 / 62)


def test_rrf_deduplicates_one_strategy_and_breaks_ties_deterministically() -> None:
    alpha = hit("inventory.alpha", 1.0)
    beta = hit("inventory.beta", 1.0)

    fused = ReciprocalRankFusion(rank_constant=60).fuse(
        ((beta, beta), (alpha,)),
        limit=2,
    )

    assert [item.tool.canonical_name for item in fused] == [
        "inventory.alpha",
        "inventory.beta",
    ]
    assert fused[0].rank == fused[1].rank == pytest.approx(1 / 61)


def test_rrf_validates_algorithm_parameters() -> None:
    with pytest.raises(ValueError, match="rank constant"):
        ReciprocalRankFusion(rank_constant=0)
    with pytest.raises(ValueError, match="result limit"):
        ReciprocalRankFusion().fuse((), limit=0)
