import logging
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.messaging import start_consumer, stop_consumer
from app.routes.email import router as email_router
from app.routes.health import router as health_router

logger = logging.getLogger("uvicorn.error")
logger.info("Email service main module loaded - about to create app")

app = FastAPI(title="Email Service", version="1.0.0")

logger.info("Email service main module loaded - app created")

app.include_router(health_router)
app.include_router(email_router)

logger.info("Email service main module loaded - routers included")

Instrumentator().instrument(app).expose(app, include_in_schema=False)

logger.info("Email service main module loaded - instrumentator configured")


@app.on_event("startup")
def startup_event() -> None:
    try:
        logger.info("FastAPI startup event: starting email consumer")
        start_consumer()
    except Exception as e:
        logger.exception(f"Failed to start email consumer: {e}")


@app.on_event("shutdown")
def shutdown_event() -> None:
    logger.info("FastAPI shutdown event: stopping email consumer")
    stop_consumer()
