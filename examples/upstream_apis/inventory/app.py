"""用于验证库存查询、幂等配置与非幂等预留映射的轻量 Inventory API。"""

from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW = "low"
    OUT_OF_STOCK = "out_of_stock"


class StockLevel(BaseModel):
    sku: str
    warehouse_id: str
    on_hand: int
    reserved: int
    available: int
    status: StockStatus


class CreateReservationRequest(BaseModel):
    warehouse_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=1000)


class Reservation(BaseModel):
    reservation_id: str
    sku: str
    warehouse_id: str
    order_id: str
    quantity: int
    status: str


class SetReorderLevelRequest(BaseModel):
    warehouse_id: str = Field(min_length=1)
    reorder_level: int = Field(ge=0, le=1000)


class ReorderLevel(BaseModel):
    sku: str
    warehouse_id: str
    reorder_level: int


STOCK = {
    ("laptop-pro-14", "shanghai-01"): StockLevel(
        sku="laptop-pro-14",
        warehouse_id="shanghai-01",
        on_hand=100,
        reserved=20,
        available=80,
        status=StockStatus.IN_STOCK,
    ),
    ("scanner-usb", "shanghai-01"): StockLevel(
        sku="scanner-usb",
        warehouse_id="shanghai-01",
        on_hand=5,
        reserved=3,
        available=2,
        status=StockStatus.LOW,
    ),
}

REORDER_LEVELS: dict[tuple[str, str], int] = {}
IDEMPOTENT_RESULTS: dict[str, tuple[tuple[str, str, int], ReorderLevel]] = {}
REORDER_LEVEL_REQUESTS: list[str] = []

app = FastAPI(title="Inventory API", version="1.0.0")


@app.get(
    "/inventory/{sku}",
    operation_id="getStatus",
    response_model=StockLevel,
)
async def get_stock_status(
    sku: str,
    warehouse_id: Annotated[str, Query(min_length=1)],
) -> StockLevel:
    stock = STOCK.get((sku, warehouse_id))
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    return stock


@app.put(
    "/inventory/{sku}/reorder-level",
    operation_id="setReorderLevel",
    response_model=ReorderLevel,
    openapi_extra={"x-nexusmcp-side-effect": "idempotent_write"},
)
async def set_reorder_level(
    sku: str,
    request: SetReorderLevelRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> ReorderLevel:
    if (sku, request.warehouse_id) not in STOCK:
        raise HTTPException(status_code=404, detail="Stock item not found")
    REORDER_LEVEL_REQUESTS.append(idempotency_key)
    fingerprint = (sku, request.warehouse_id, request.reorder_level)
    existing = IDEMPOTENT_RESULTS.get(idempotency_key)
    if existing is not None:
        if existing[0] != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key payload conflict")
        return existing[1]
    REORDER_LEVELS[(sku, request.warehouse_id)] = request.reorder_level
    result = ReorderLevel(
        sku=sku,
        warehouse_id=request.warehouse_id,
        reorder_level=request.reorder_level,
    )
    IDEMPOTENT_RESULTS[idempotency_key] = (fingerprint, result)
    return result


@app.post(
    "/inventory/{sku}/reservations",
    operation_id="reserveStock",
    response_model=Reservation,
    openapi_extra={"x-nexusmcp-side-effect": "non_idempotent_write"},
)
async def reserve_stock(sku: str, request: CreateReservationRequest) -> Reservation:
    stock = STOCK.get((sku, request.warehouse_id))
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    if request.quantity > stock.available:
        raise HTTPException(status_code=409, detail="Insufficient available stock")
    return Reservation(
        reservation_id=f"res-{request.order_id}-{sku}",
        sku=sku,
        warehouse_id=request.warehouse_id,
        order_id=request.order_id,
        quantity=request.quantity,
        status="created",
    )
