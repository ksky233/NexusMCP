"""MCP Scope Audit Evidence 的单一映射规则。"""

import pytest

from nexusmcp.modules.audit.scope import McpScopeAuditEvidence


def test_scope_evidence_maps_root_scoped_and_denial_reasons() -> None:
    assert McpScopeAuditEvidence(scope_type="root").metadata() == {
        "mcp_scope_type": "root",
        "scope_reason_code": "granted_toolset_union",
    }
    scoped = McpScopeAuditEvidence(
        scope_type="toolset",
        toolset_id="toolset-1",
        toolset_revision=3,
        toolset_slug="operations",
    )
    assert scoped.metadata() == {
        "mcp_scope_type": "toolset",
        "scope_reason_code": "active_toolset_grant",
        "toolset_id": "toolset-1",
        "toolset_revision": 3,
        "toolset_slug": "operations",
    }
    assert (
        scoped.metadata(denial_reason_code="toolset_access_denied")["scope_reason_code"]
        == "toolset_access_denied"
    )


@pytest.mark.parametrize(
    ("scope_type", "toolset_id", "toolset_revision"),
    [
        ("root", "toolset-1", None),
        ("toolset", "toolset-1", None),
        ("toolset", None, 1),
    ],
)
def test_scope_evidence_rejects_incomplete_context(
    scope_type: str,
    toolset_id: str | None,
    toolset_revision: int | None,
) -> None:
    with pytest.raises(ValueError):
        McpScopeAuditEvidence(
            scope_type=scope_type,
            toolset_id=toolset_id,
            toolset_revision=toolset_revision,
        )
