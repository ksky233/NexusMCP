"""覆盖首条 OpenAPI 纵向切片参数形态的轻量 Employee Directory API。"""

from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    LEAVE = "leave"
    TERMINATED = "terminated"


class Employee(BaseModel):
    employee_id: str
    name: str
    department: str
    status: EmploymentStatus
    email: str


class EmployeeSearchFilter(BaseModel):
    department: str | None = None
    statuses: list[EmploymentStatus] = Field(default_factory=list)


class SearchEmployeesRequest(BaseModel):
    filter: EmployeeSearchFilter
    limit: int = Field(default=20, ge=1, le=100)


EMPLOYEES = (
    Employee(
        employee_id="emp-001",
        name="Ada Chen",
        department="engineering",
        status=EmploymentStatus.ACTIVE,
        email="ada.chen@example.test",
    ),
    Employee(
        employee_id="emp-002",
        name="Lin Zhao",
        department="operations",
        status=EmploymentStatus.LEAVE,
        email="lin.zhao@example.test",
    ),
    Employee(
        employee_id="emp-003",
        name="Mina Wu",
        department="engineering",
        status=EmploymentStatus.ACTIVE,
        email="mina.wu@example.test",
    ),
)

app = FastAPI(title="Employee Directory API", version="1.0.0")


@app.get(
    "/employees/{employee_id}",
    operation_id="getEmployee",
    response_model=Employee,
)
async def get_employee(employee_id: str) -> Employee:
    for employee in EMPLOYEES:
        if employee.employee_id == employee_id:
            return employee
    raise HTTPException(status_code=404, detail="Employee not found")


@app.get(
    "/employees",
    operation_id="listEmployees",
    response_model=list[Employee],
)
async def list_employees(
    department: Annotated[str | None, Query()] = None,
    status: Annotated[EmploymentStatus | None, Query()] = None,
) -> list[Employee]:
    return [
        employee
        for employee in EMPLOYEES
        if (department is None or employee.department == department)
        and (status is None or employee.status is status)
    ]


@app.post(
    "/employees/search",
    operation_id="searchEmployees",
    response_model=list[Employee],
    openapi_extra={"x-nexusmcp-side-effect": "read_only"},
)
async def search_employees(
    request: SearchEmployeesRequest,
    x_directory_region: Annotated[str, Header(alias="X-Directory-Region")] = "cn",
) -> list[Employee]:
    """POST Search 用扩展显式声明 read_only，避免只按 HTTP Method 猜副作用。"""

    statuses = set(request.filter.statuses)
    matches = [
        employee
        for employee in EMPLOYEES
        if (request.filter.department is None or employee.department == request.filter.department)
        and (not statuses or employee.status in statuses)
    ]
    # Region 仅用于证明 Header Mapping，不引入真实地区数据分支。
    _ = x_directory_region
    return matches[: request.limit]
