"""MCP Request Scope 的统一 Audit Metadata 映射。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class McpScopeAuditEvidence:
    scope_type: str
    toolset_id: str | None = None
    toolset_revision: int | None = None
    toolset_slug: str | None = None

    def __post_init__(self) -> None:
        if self.scope_type not in {"root", "toolset"}:
            raise ValueError("audit MCP scope type was invalid")
        if self.scope_type == "root" and any(
            value is not None
            for value in (self.toolset_id, self.toolset_revision, self.toolset_slug)
        ):
            raise ValueError("root audit scope must not contain toolset context")
        if (self.toolset_id is None) != (self.toolset_revision is None):
            raise ValueError("audit toolset id and revision must appear together")
        if self.toolset_revision is not None and self.toolset_revision <= 0:
            raise ValueError("audit toolset revision must be positive")

    def metadata(self, *, denial_reason_code: str | None = None) -> dict[str, str | int]:
        values: dict[str, str | int] = {
            "mcp_scope_type": self.scope_type,
            "scope_reason_code": denial_reason_code
            or (
                "active_toolset_grant" if self.scope_type == "toolset" else "granted_toolset_union"
            ),
        }
        if self.toolset_id is not None:
            values["toolset_id"] = self.toolset_id
        if self.toolset_revision is not None:
            values["toolset_revision"] = self.toolset_revision
        if self.toolset_slug is not None:
            values["toolset_slug"] = self.toolset_slug
        return values
