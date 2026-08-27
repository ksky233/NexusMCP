"""Retrieval Eval Dataset 校验与指标公式测试。"""

from pathlib import Path

import pytest

from nexusmcp.modules.tool_search.evaluation import (
    RetrievalEvalCase,
    RetrievalEvalObservation,
    RetrievalEvalStrategy,
    evaluate_retrieval,
    load_retrieval_eval_cases,
)

CASES_PATH = Path(__file__).resolve().parents[4] / "evals" / "tool_search" / "retrieval_cases.json"


def test_versioned_dataset_is_small_labeled_and_covers_all_demo_tools() -> None:
    cases = load_retrieval_eval_cases(CASES_PATH)

    assert len(cases) == 24
    assert {case.category for case in cases} == {
        "exact_keyword",
        "semantic_fuzzy",
        "cross_language",
        "filter",
        "no_match",
    }
    assert set().union(*(case.relevant_tools for case in cases)) == {
        "directory.get_employee",
        "directory.list_employees",
        "directory.search_employees",
        "ops.get_status",
        "ops.acknowledge_incident",
        "inventory.get_status",
        "inventory.reserve_stock",
        "inventory.set_reorder_level",
    }


def test_metrics_use_positive_cases_and_report_no_match_and_leakage_separately() -> None:
    cases = (
        RetrievalEvalCase(
            id="case-a",
            category="exact",
            query="alpha",
            relevance=(("tool.alpha", 3),),
            lexical_expected=True,
        ),
        RetrievalEvalCase(
            id="case-b",
            category="semantic",
            query="beta",
            relevance=(("tool.beta", 3),),
            lexical_expected=False,
            forbidden_tools=("tool.hidden",),
        ),
        RetrievalEvalCase(
            id="case-none",
            category="no_match",
            query="nothing",
            relevance=(),
            lexical_expected=True,
        ),
    )
    observations = (
        RetrievalEvalObservation(
            case_id="case-a",
            strategy=RetrievalEvalStrategy.HYBRID,
            ranked_tools=("tool.alpha",),
            latency_ms=1.0,
        ),
        RetrievalEvalObservation(
            case_id="case-b",
            strategy=RetrievalEvalStrategy.HYBRID,
            ranked_tools=("tool.hidden", "tool.beta"),
            latency_ms=2.0,
        ),
        RetrievalEvalObservation(
            case_id="case-none",
            strategy=RetrievalEvalStrategy.HYBRID,
            ranked_tools=(),
            latency_ms=3.0,
        ),
    )

    metrics = evaluate_retrieval(
        cases,
        observations,
        strategy=RetrievalEvalStrategy.HYBRID,
        k=3,
    )

    assert metrics.top_1_accuracy == 0.5
    assert metrics.hit_at_k == 1.0
    assert metrics.mrr == 0.75
    assert metrics.ndcg_at_k == pytest.approx((1.0 + 1.0 / 1.584962500721156) / 2)
    assert metrics.no_match_accuracy == 1.0
    assert metrics.latency_p50_ms == 2.0
    assert metrics.latency_p95_ms == pytest.approx(2.9)
    assert metrics.unauthorized_leakage_count == 1
    assert metrics.unauthorized_leakage_rate == pytest.approx(1 / 3)


def test_metrics_reject_incomplete_observation_matrix() -> None:
    case = RetrievalEvalCase(
        id="case-a",
        category="exact",
        query="alpha",
        relevance=(("tool.alpha", 1),),
        lexical_expected=True,
    )

    with pytest.raises(ValueError, match="cover the dataset"):
        evaluate_retrieval(
            (case,),
            (),
            strategy=RetrievalEvalStrategy.LEXICAL,
        )
