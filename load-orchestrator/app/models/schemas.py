from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChaosConfig(BaseModel):
    enabled: bool = False
    target_service: Literal["email-service", "inventory-service"] = "email-service"
    outage_seconds: int = Field(60, ge=5, le=600)
    recovery_replicas: int = Field(2, ge=1, le=50)


class StartRunRequest(BaseModel):
    total_requests: int = Field(2000, ge=1)
    vus: int = Field(100, ge=1, le=10000)
    max_duration: str = "2m"
    unique_users: int = Field(1000, ge=1)
    order_base_url: str = "http://order-service.kafka-lab.svc.cluster.local:8000"
    target_item: str = Field("pencil", description="Product to order (pencil, notebook, eraser)")
    item_quantity: int = Field(1, ge=1, le=1000)
    chaos: ChaosConfig = ChaosConfig()


class RunSummary(BaseModel):
    run_id: str
    job_name: str
    namespace: str
    status: str
    created_at: datetime
    request: StartRunRequest


class StartRunResponse(BaseModel):
    run: RunSummary
    message: str


class StopRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class RunDetails(BaseModel):
    run: RunSummary
    active: bool
    succeeded: int | None = None
    failed: int | None = None
    completion_time: datetime | None = None
    last_log_excerpt: str | None = None
