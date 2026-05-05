from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.messaging import close_producer
from app.cache.redis_client import close_redis
from app.routes.health import router as health_router
from app.routes.orders import router as orders_router
from app.routes.config import router as config_router

app = FastAPI(title="Order Service", version="1.0.0")

app.include_router(health_router)
app.include_router(orders_router)
app.include_router(config_router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.on_event("shutdown")
def shutdown_event() -> None:
    close_producer()
    close_redis()
