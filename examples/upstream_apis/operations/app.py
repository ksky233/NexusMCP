"""用于验证运维查询与幂等写入映射的轻量 Operations API。"""

from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Incident(BaseModel):
    incident_id: str
    service: str
    status: IncidentStatus
    severity: IncidentSeverity
    summary: str


class AcknowledgeIncidentRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


INCIDENTS = {
    "inc-001": Incident(
        incident_id="inc-001",
        service="checkout-api",
        status=IncidentStatus.INVESTIGATING,
        severity=IncidentSeverity.HIGH,
        summary="Checkout latency above threshold",
    ),
    "inc-002": Incident(
        incident_id="inc-002",
        service="inventory-sync",
        status=IncidentStatus.RESOLVED,
        severity=IncidentSeverity.MEDIUM,
        summary="Inventory synchronization delayed",
    ),
}

app = FastAPI(title="IT Operations API", version="1.0.0")


@app.get(
    "/incidents/{incident_id}",
    operation_id="getStatus",
    response_model=Incident,
)
async def get_incident_status(incident_id: str) -> Incident:
    incident = INCIDENTS.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post(
    "/incidents/{incident_id}/acknowledge",
    operation_id="acknowledgeIncident",
    response_model=Incident,
    openapi_extra={"x-nexusmcp-side-effect": "idempotent_write"},
)
async def acknowledge_incident(
    incident_id: str,
    request: AcknowledgeIncidentRequest,
    operator_id: Annotated[str, Header(alias="X-Operator-Id", min_length=1)],
) -> Incident:
    incident = INCIDENTS.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    # Fake API 不持久化状态；重复调用返回相同业务结果，用于表达幂等写语义。
    _ = (request.note, operator_id)
    return incident.model_copy(update={"status": IncidentStatus.ACKNOWLEDGED})
