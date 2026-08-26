"""用于验证库存查询和非幂等预留写入映射的轻量 Inventory API。"""

from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
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
