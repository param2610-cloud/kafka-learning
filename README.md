# FastAPI Microservices: Order, Email, Inventory

This project contains three services connected with direct API calls:

- Order Service creates orders
- Email Service sends order confirmations
- Inventory Service reduces stock

It also includes an in-cluster Load Orchestrator service:

- Starts/stops k6 load runs as Kubernetes Jobs
- Optionally simulates outage by scaling down email or inventory deployment during a run
- Provides a simple browser UI for scenario control and status

Flow:

1. Client calls `POST /orders` on Order Service.
2. Order Service creates an order in memory.
3. Order Service calls Email Service `POST /confirm-order`.
4. Order Service calls Inventory Service `POST /reduce-stock`.

This repo now includes resilience controls for load and chaos testing:

- Configurable retries with exponential backoff in Order Service.
- Failure-mode toggles in Email and Inventory services.
- Kubernetes manifests with CPU and memory requests/limits.
- A k6 script to drive up to 1,000,000 order requests.

## Services and Ports

- Order Service: `http://localhost:8000`
- Email Service: `http://localhost:8001`
- Inventory Service: `http://localhost:8002`
- Load Orchestrator UI (Kubernetes NodePort): `http://localhost:30081`
- Prometheus UI (Kubernetes NodePort): `http://localhost:30090`
- Grafana UI (Kubernetes NodePort): `http://localhost:30300` (`admin` / `admin`)

## Run with Docker Compose

From repository root:

```bash
docker compose up --build
```

Retry behavior for Order Service is configured with these environment variables:

- `DOWNSTREAM_MAX_RETRIES` (default `4`)
- `DOWNSTREAM_INITIAL_BACKOFF_SECONDS` (default `0.1`)
- `DOWNSTREAM_BACKOFF_MULTIPLIER` (default `2.0`)
- `DOWNSTREAM_MAX_BACKOFF_SECONDS` (default `2.0`)
- `DOWNSTREAM_REQUEST_TIMEOUT_SECONDS` (default `2.0`)

## Example Request

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u-123",
    "email": "user@example.com",
    "items": [
      {"product_id": "pencil", "quantity": 2},
      {"product_id": "notebook", "quantity": 1}
    ]
  }'
```

## Useful Endpoints

- Order health: `GET /health` on port 8000
- Email health: `GET /health` on port 8001
- Inventory health: `GET /health` on port 8002
- Inventory stock view: `GET /stock` on port 8002
- Email failure mode: `GET /failure-mode` and `POST /failure-mode` on port 8001
- Inventory failure mode: `GET /failure-mode` and `POST /failure-mode` on port 8002
- Crash trigger (chaos): `POST /simulate-crash` on email/inventory services

Failure mode request body:

```json
{
  "enabled": true,
  "mode": "error",
  "error_rate": 1.0,
  "delay_seconds": 0
}
```

`mode` can be:

- `error`: fail requests using HTTP 503 based on `error_rate`
- `delay`: add response delay using `delay_seconds`

## Run Tests Locally

Run tests from each service directory:

```bash
pytest -q
```

## Kubernetes Setup (CPU/Memory Controlled)

Prerequisites:

- Kubernetes cluster (Docker Desktop Kubernetes, Minikube, Kind, or cloud)
- `kubectl`
- `k6` for load generation

From repo root:

```powershell
.\scripts\deploy-k8s.ps1
```

After deploy, open:

`http://localhost:30081`

Use the UI to:

1. Configure total requests, VUs, duration, and target URL.
2. Toggle chaos mode and choose target service.
3. Start a run and observe logs/status from the dashboard.

## Visualization and Bottleneck Detection

The `observability.yaml` stack provisions Prometheus and Grafana with a ready dashboard called:

- `Kafka Lab Service Health`

Dashboard panels include:

1. Request rate by service
2. 5xx error ratio by service
3. P95 latency by service
4. In-progress requests by service

After deployment, open Grafana at `http://localhost:30300` and use the pre-provisioned dashboard to watch spike behavior, downtime windows, and recovery.

Expose order service locally:

```powershell
kubectl -n kafka-lab port-forward svc/order-service 8000:8000
```

Kubernetes manifests are in `k8s/` and include:

- Deployment + Service for all three services
- Resource requests/limits for each container
- HorizontalPodAutoscaler definitions

## Million Request Chaos Scenario

Terminal 1: expose Order Service

```powershell
kubectl -n kafka-lab port-forward svc/order-service 8000:8000
```

Alternative (recommended): use Load Orchestrator UI at `http://localhost:30081` to run in-cluster k6 jobs without local port-forward load bottleneck.

Terminal 2: start heavy load (1,000,000 requests)

```powershell
k6 run .\load\k6\order_spike.js -e ORDER_BASE_URL=http://localhost:8000 -e TOTAL_REQUESTS=1000000 -e VUS=2000 -e MAX_DURATION=20m -e UNIQUE_USERS=1000
```

Terminal 3: simulate outage while load is active

```powershell
.\scripts\run-chaos-outage.ps1 -TargetService email-service -OutageSeconds 90 -RecoveryReplicas 2
```

or

```powershell
.\scripts\run-chaos-outage.ps1 -TargetService inventory-service -OutageSeconds 90 -RecoveryReplicas 2
```

Expected behavior:

- During outage, Order Service retries downstream calls with exponential backoff.
- Some requests will become `partial-failure` while downstream is unavailable.
- After recovery, retryable calls should begin succeeding again.

Optional: toggle failure mode without scaling deployments

```powershell
.\scripts\set-failure-mode.ps1 -Service email -Enabled $true -Mode error -ErrorRate 1.0
.\scripts\set-failure-mode.ps1 -Service email -Enabled $false
```
