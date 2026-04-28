from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.messaging import start_consumer, stop_consumer
from app.routes.email import router as email_router
from app.routes.health import router as health_router

app = FastAPI(title="Email Service", version="1.0.0")

app.include_router(health_router)
app.include_router(email_router)

Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.on_event("startup")
def startup_event() -> None:
    start_consumer()


@app.on_event("shutdown")
def shutdown_event() -> None:
    stop_consumer()
