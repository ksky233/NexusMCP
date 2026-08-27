"""不同 Retrieval Strategy 的 Rank-Based Fusion。"""

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit


class ReciprocalRankFusion:
    """只依赖名次融合候选，避免直接混合不同量纲的 Raw Score。"""

    def __init__(self, *, rank_constant: int = 60) -> None:
        if rank_constant <= 0:
            raise ValueError("RRF rank constant must be positive")
        self._rank_constant = rank_constant

    def fuse(
        self,
        rankings: tuple[tuple[PublishedToolSearchHit, ...], ...],
        *,
        limit: int,
    ) -> tuple[PublishedToolSearchHit, ...]:
        if limit <= 0:
            raise ValueError("RRF result limit must be positive")
        scores: dict[str, float] = {}
        tools: dict[str, PublishedToolSearchHit] = {}
        for ranking in rankings:
            seen_in_ranking: set[str] = set()
            for position, hit in enumerate(ranking, start=1):
                identity = hit.tool.tool_version_id
                # 单一策略的重复行不能人为放大融合分数。
                if identity in seen_in_ranking:
                    continue
                seen_in_ranking.add(identity)
                tools.setdefault(identity, hit)
                scores[identity] = scores.get(identity, 0.0) + 1.0 / (
                    self._rank_constant + position
                )
        ordered = sorted(
            scores,
            key=lambda identity: (
                -scores[identity],
                tools[identity].tool.canonical_name,
                identity,
            ),
        )
        return tuple(
            PublishedToolSearchHit(tool=tools[identity].tool, rank=scores[identity])
            for identity in ordered[:limit]
        )
