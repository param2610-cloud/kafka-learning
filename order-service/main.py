from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routes.health import router as health_router
from app.routes.orders import router as orders_router

app = FastAPI(title="Order Service", version="1.0.0")

app.include_router(health_router)
app.include_router(orders_router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)
