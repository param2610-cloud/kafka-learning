# FastAPI Microservices: Order, Email, Inventory

This project contains three services connected through Kafka events (with optional synchronous fallback):

- Order Service creates orders
- Email Service sends order confirmations
- Inventory Service reduces stock

It also includes an in-cluster Load Orchestrator service:

- Starts/stops k6 load runs as Kubernetes Jobs
- Optionally simulates outage by scaling down email or inventory deployment during a run
- Provides a simple browser UI for scenario control and status

Flow (default Kafka mode):

1. Client calls `POST /orders` on Order Service.
2. Order Service creates an order in memory.
3. Order Service publishes an `order.created` event to Kafka.
4. Email and Inventory services consume the event asynchronously and process it in background threads.

Optional compatibility mode:

- If Kafka is disabled, Order Service uses direct HTTP calls to Email and Inventory.
- If Kafka is enabled but publish fails and `KAFKA_FALLBACK_SYNC=true`, Order Service falls back to direct HTTP calls.

This repo now includes resilience controls for load and chaos testing:

- Configurable retries with exponential backoff in Order Service.
- Failure-mode toggles in Email service.
- Kubernetes manifests with CPU and memory requests/limits.
- A k6 script to drive up to 1,000,000 order requests.

## Services and Ports

- Order Service: `http://localhost:8000`
- Email Service: `http://localhost:8001`
- Inventory Service: `http://localhost:8002`
- Kafka Broker: `localhost:9092`
- Load Orchestrator UI (Kubernetes NodePort): `http://localhost:30081`
- Prometheus UI (Kubernetes NodePort): `http://localhost:30090`
- Grafana UI (Kubernetes NodePort): `http://localhost:30300` (`admin` / `admin`)

## Run with Docker Compose

From repository root:

```bash
docker compose up --build
```

Order requests are asynchronous by default in compose (`KAFKA_ENABLED=true`, `KAFKA_FALLBACK_SYNC=false`), so the API response typically returns `order.status = queued` after the event is published.

Kafka-related environment variables:

- `KAFKA_ENABLED` (default `false`)
- `KAFKA_BOOTSTRAP_SERVERS` (default `kafka:9092`)
- `KAFKA_ORDER_CREATED_TOPIC` (default `orders.created`)
- `KAFKA_FALLBACK_SYNC` (default `false`)
- `EMAIL_PROVIDER_API_DELAY_SECONDS` (default `0`) simulates external email provider API latency in Email Service
- `INVENTORY_DB_CALL_DELAY_SECONDS` (default `0`) simulates DB call latency in Inventory Service

Kafka partition planning for scale-out:

- Consumer parallelism in one consumer group is capped by topic partition count.
- If Email Service can scale to 16 replicas, keep `orders.created` at at least 16 partitions.
- Set partitions before scaling up consumers to avoid idle replicas.
- This repo pre-creates `orders.created` with 16 partitions in both Docker Compose and Kubernetes.
- If `orders.created` already exists with fewer partitions, run a one-time `--alter` command to increase it.

If you need to increase partitions further (example: 24):

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --alter --topic orders.created --partitions 24
```

Note: partitions can be increased, not decreased.

Retry behavior for direct HTTP downstream calls is configured with these environment variables:

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
- Crash trigger (chaos): `POST /simulate-crash` on email/inventory services

Failure mode request body (email service):

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

The k6 job now uses a larger default memory budget to avoid `OOMKilled` during heavier runs. If you need to tune the runner for a specific cluster, set these environment variables before starting the orchestrator service:

- `K6_CPU_REQUEST`
- `K6_CPU_LIMIT`
- `K6_MEMORY_REQUEST`
- `K6_MEMORY_LIMIT`

Defaults are `500m`, `2000m`, `1Gi`, and `4Gi` respectively.

## Visualization and Bottleneck Detection

The `observability.yaml` stack provisions Prometheus and Grafana with a ready dashboard called:

- `Kafka Lab Service Health`

Dashboard panels include:

1. All services throughput by service
2. Email service event processing rate
3. Inventory service event processing rate
4. Order service request rate
5. CPU usage by service (order, email, inventory)
6. Kafka event resolution counts (produced, processed, and backlog)

After deployment, open Grafana at `http://localhost:30300` and use the pre-provisioned dashboard to watch spike behavior, downtime windows, and recovery.

Expose order service locally:

```powershell
kubectl -n kafka-lab port-forward svc/order-service 8000:8000
```

Kubernetes manifests are in `k8s/` and include:

- Kafka Deployment + Service (single-node KRaft)
- Deployment + Service for all three services
- Resource requests/limits for each container
- HorizontalPodAutoscaler definitions
- Kafka topic init Job that pre-creates `orders.created` with 16 partitions

## Million Request Chaos Scenario

Terminal 1: expose Order Service

```powershell
kubectl -n kafka-lab port-forward svc/order-service 8000:8000
```

Alternative (recommended): use Load Orchestrator UI at `http://localhost:30081` to run in-cluster k6 jobs without local port-forward load bottleneck.

k6 load test environment variables:

- `ORDER_BASE_URL` (default `http://localhost:8000`) - Order service endpoint
- `TOTAL_REQUESTS` (default `1000000`) - Total order requests to generate
- `VUS` (default `2000`) - Virtual users (concurrent load)
- `MAX_DURATION` (default `20m`) - Maximum test duration
- `UNIQUE_USERS` (default `1000`) - Pool of unique user IDs
- `TARGET_ITEM` (default `pencil`) - Product ID to order (e.g., `pencil`, `notebook`, `eraser`)
- `ITEM_QUANTITY` (default `1`) - Quantity of item per order

Terminal 2: start heavy load ordering a specific item (1,000,000 requests of pencils)

```powershell
k6 run .\load\k6\order_spike.js -e ORDER_BASE_URL=http://localhost:8000 -e TOTAL_REQUESTS=1000000 -e VUS=2000 -e MAX_DURATION=20m -e UNIQUE_USERS=1000 -e TARGET_ITEM=pencil -e ITEM_QUANTITY=1
```

Alternative: order notebooks instead

```powershell
k6 run .\load\k6\order_spike.js -e ORDER_BASE_URL=http://localhost:8000 -e TOTAL_REQUESTS=1000000 -e VUS=2000 -e MAX_DURATION=20m -e UNIQUE_USERS=1000 -e TARGET_ITEM=notebook -e ITEM_QUANTITY=5
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

- With Kafka mode (`KAFKA_ENABLED=true`), `POST /orders` keeps returning quickly with `status=queued` while consumers handle work asynchronously.
- During email or inventory outage, events remain in Kafka and processing resumes after service recovery.
- With compatibility mode (`KAFKA_ENABLED=false`), behavior reverts to synchronous retries and possible `partial-failure` responses.

Optional: toggle failure mode without scaling deployments

```powershell
.\scripts\set-failure-mode.ps1 -Service email -Enabled $true -Mode error -ErrorRate 1.0
.\scripts\set-failure-mode.ps1 -Service email -Enabled $false
```
