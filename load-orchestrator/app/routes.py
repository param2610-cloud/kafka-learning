from fastapi import APIRouter, HTTPException

from app.models.schemas import RunDetails, StartRunRequest, StartRunResponse, StopRunResponse
from app.services import runner

router = APIRouter(prefix="/api", tags=["orchestrator"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "load-orchestrator", "status": "ok"}


@router.post("/runs", response_model=StartRunResponse)
def start_run(payload: StartRunRequest) -> StartRunResponse:
    summary = runner.start_run(payload)
    return StartRunResponse(run=summary, message="k6 run started")


@router.get("/runs")
def list_runs() -> dict[str, list]:
    return {"runs": runner.list_runs()}


@router.get("/runs/{run_id}", response_model=RunDetails)
def get_run(run_id: str) -> RunDetails:
    details = runner.get_run_status(run_id)
    if not details:
        raise HTTPException(status_code=404, detail="run not found")
    return RunDetails(**details)


@router.delete("/runs/{run_id}", response_model=StopRunResponse)
def stop_run(run_id: str) -> StopRunResponse:
    stopped = runner.stop_run(run_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="run not found")
    return StopRunResponse(run_id=run_id, status="stopped", message="run stopped")
