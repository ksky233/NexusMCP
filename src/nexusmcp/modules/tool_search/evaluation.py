"""Tool Retrieval Eval Dataset、Observation 与确定性指标计算。"""

import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.hybrid_search import SearchHybridTools
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools
from nexusmcp.shared.request_context import RequestContext


class RetrievalEvalStrategy(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    id: str
    category: str
    query: str
    relevance: tuple[tuple[str, int], ...]
    lexical_expected: bool
    namespace: str | None = None
    side_effect: ToolSideEffect | None = None
    forbidden_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.category.strip() or not self.query.strip():
            raise ValueError("retrieval eval case identity and query must not be blank")
        names = [name for name, _grade in self.relevance]
        if len(names) != len(set(names)):
            raise ValueError("retrieval eval relevance labels must be unique")
        if any(not name.strip() or grade <= 0 for name, grade in self.relevance):
            raise ValueError("retrieval eval relevance labels must be positive")
        if len(self.forbidden_tools) != len(set(self.forbidden_tools)):
            raise ValueError("retrieval eval forbidden tools must be unique")
        if set(names) & set(self.forbidden_tools):
            raise ValueError("relevant tools must not also be forbidden")

    @property
    def relevant_tools(self) -> frozenset[str]:
        return frozenset(name for name, _grade in self.relevance)


@dataclass(frozen=True, slots=True)
class RetrievalEvalObservation:
    case_id: str
    strategy: RetrievalEvalStrategy
    ranked_tools: tuple[str, ...]
    latency_ms: float

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("retrieval eval observation case id must not be blank")
        if self.latency_ms < 0 or not math.isfinite(self.latency_ms):
            raise ValueError("retrieval eval latency must be finite and non-negative")
        if len(self.ranked_tools) != len(set(self.ranked_tools)):
            raise ValueError("retrieval eval ranked tools must not contain duplicates")


@dataclass(frozen=True, slots=True)
class RetrievalEvalMetrics:
    strategy: RetrievalEvalStrategy
    case_count: int
    positive_case_count: int
    no_match_case_count: int
    top_1_accuracy: float
    hit_at_k: float
    mrr: float
    ndcg_at_k: float
    no_match_accuracy: float
    latency_p50_ms: float
    latency_p95_ms: float
    unauthorized_leakage_count: int
    unauthorized_leakage_rate: float
    k: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["strategy"] = self.strategy.value
        return payload


def load_retrieval_eval_cases(path: Path) -> tuple[RetrievalEvalCase, ...]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("retrieval eval dataset root was invalid")
    cases = tuple(_parse_case(item) for item in payload["cases"])
    case_ids = [case.id for case in cases]
    if not cases or len(case_ids) != len(set(case_ids)):
        raise ValueError("retrieval eval case ids must be non-empty and unique")
    return cases


def evaluate_retrieval(
    cases: tuple[RetrievalEvalCase, ...],
    observations: tuple[RetrievalEvalObservation, ...],
    *,
    strategy: RetrievalEvalStrategy,
    k: int = 3,
) -> RetrievalEvalMetrics:
    if k <= 0:
        raise ValueError("retrieval eval k must be positive")
    selected = [observation for observation in observations if observation.strategy is strategy]
    by_case = {observation.case_id: observation for observation in selected}
    if len(by_case) != len(selected):
        raise ValueError("retrieval eval observations contained duplicate strategy cases")
    expected_ids = {case.id for case in cases}
    if set(by_case) != expected_ids:
        raise ValueError("retrieval eval observations did not cover the dataset")

    positives = [case for case in cases if case.relevance]
    no_matches = [case for case in cases if not case.relevance]
    if not positives:
        raise ValueError("retrieval eval dataset must contain positive cases")
    top_1 = 0
    hit_at_k = 0
    reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0
    no_match_correct = 0
    leakage_count = 0
    returned_count = 0
    for case in cases:
        ranked = by_case[case.id].ranked_tools
        returned_count += len(ranked)
        forbidden = set(case.forbidden_tools)
        leakage_count += sum(name in forbidden for name in ranked)
        if not case.relevance:
            no_match_correct += not ranked
            continue
        relevant = case.relevant_tools
        top_1 += bool(ranked and ranked[0] in relevant)
        hit_at_k += any(name in relevant for name in ranked[:k])
        first_relevant_rank = next(
            (position for position, name in enumerate(ranked, start=1) if name in relevant),
            None,
        )
        if first_relevant_rank is not None:
            reciprocal_rank_sum += 1.0 / first_relevant_rank
        ndcg_sum += _ndcg_at_k(case, ranked, k)

    positive_count = len(positives)
    latencies = tuple(by_case[case.id].latency_ms for case in cases)
    return RetrievalEvalMetrics(
        strategy=strategy,
        case_count=len(cases),
        positive_case_count=positive_count,
        no_match_case_count=len(no_matches),
        top_1_accuracy=top_1 / positive_count,
        hit_at_k=hit_at_k / positive_count,
        mrr=reciprocal_rank_sum / positive_count,
        ndcg_at_k=ndcg_sum / positive_count,
        no_match_accuracy=(no_match_correct / len(no_matches) if no_matches else 1.0),
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        unauthorized_leakage_count=leakage_count,
        unauthorized_leakage_rate=(leakage_count / returned_count if returned_count else 0.0),
        k=k,
    )


async def collect_retrieval_observations(
    cases: tuple[RetrievalEvalCase, ...],
    *,
    context: RequestContext,
    lexical: SearchPublishedTools,
    vector: SearchVectorTools,
    hybrid: SearchHybridTools,
    limit: int = 3,
) -> tuple[RetrievalEvalObservation, ...]:
    """按同一 Query Matrix 收集三种内部 Strategy 的排名与本地检索延迟。"""

    if limit <= 0:
        raise ValueError("retrieval eval observation limit must be positive")
    observations: list[RetrievalEvalObservation] = []
    for case in cases:
        query = SearchPublishedToolsQuery(
            context=context,
            text=case.query,
            limit=limit,
            namespace=case.namespace,
            side_effect=case.side_effect,
        )
        for strategy in RetrievalEvalStrategy:
            started_at = perf_counter()
            if strategy is RetrievalEvalStrategy.LEXICAL:
                hits = await lexical.execute(query)
            elif strategy is RetrievalEvalStrategy.VECTOR:
                hits = (await vector.execute(query)).hits
            else:
                hits = await hybrid.execute(query)
            observations.append(
                RetrievalEvalObservation(
                    case_id=case.id,
                    strategy=strategy,
                    ranked_tools=tuple(hit.tool.canonical_name for hit in hits),
                    latency_ms=(perf_counter() - started_at) * 1000,
                )
            )
    return tuple(observations)


def _parse_case(value: object) -> RetrievalEvalCase:
    if not isinstance(value, dict):
        raise ValueError("retrieval eval case was not an object")
    relevance = value.get("relevance")
    if not isinstance(relevance, dict):
        raise ValueError("retrieval eval relevance was not an object")
    raw_side_effect = value.get("side_effect")
    return RetrievalEvalCase(
        id=_required_string(value, "id"),
        category=_required_string(value, "category"),
        query=_required_string(value, "query"),
        relevance=tuple(
            sorted(
                (
                    str(name),
                    _positive_integer(grade, "relevance grade"),
                )
                for name, grade in relevance.items()
            )
        ),
        lexical_expected=_required_boolean(value, "lexical_expected"),
        namespace=_optional_string(value, "namespace"),
        side_effect=(ToolSideEffect(raw_side_effect) if raw_side_effect is not None else None),
        forbidden_tools=_string_tuple(value.get("forbidden_tools", []), "forbidden tools"),
    )


def _ndcg_at_k(case: RetrievalEvalCase, ranked: tuple[str, ...], k: int) -> float:
    grades = dict(case.relevance)
    dcg = sum(
        (2 ** grades.get(name, 0) - 1) / math.log2(position + 1)
        for position, name in enumerate(ranked[:k], start=1)
    )
    ideal_grades = sorted(grades.values(), reverse=True)[:k]
    ideal_dcg = sum(
        (2**grade - 1) / math.log2(position + 1)
        for position, grade in enumerate(ideal_grades, start=1)
    )
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _percentile(values: tuple[float, ...], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"retrieval eval {key} must be a non-blank string")
    return item


def _optional_string(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"retrieval eval {key} must be a non-blank string")
    return item


def _required_boolean(value: dict[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"retrieval eval {key} must be a boolean")
    return item


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"retrieval eval {field_name} must be a positive integer")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"retrieval eval {field_name} must be a string list")
    return tuple(value)
