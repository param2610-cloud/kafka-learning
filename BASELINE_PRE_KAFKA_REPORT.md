# Pre-Kafka Baseline Report (Grafana Queries)

Date: 2026-04-27
Namespace: kafka-lab
Purpose: Establish the "before Kafka" baseline under the same load profile we will reuse later.

## Test Profile (Latest Rerun)

- Run ID: `49ea6ad5`
- Total requests target: `200000`
- VUs: `100`
- Max duration: `10m`
- Unique users: `1000`
- Chaos mode: `disabled`
- Target URL: `http://order-service.kafka-lab.svc.cluster.local:8000`

## Observed Run Window

From Kubernetes events for pod `k6-run-49ea6ad5-j2fqb`:

- Scheduled: `2026-04-27T12:27:10Z`
- Started: `2026-04-27T12:27:12Z`
- Stopped: `2026-04-27T12:31:39Z`
- Effective observed window: ~`267s`

## Grafana/Prometheus Queries Used

Same expressions as dashboard panels:

1. Request rate by service:
   - `sum by (job) (rate(http_requests_total[1m]))`
2. 5xx error ratio by service:
   - `sum by (job) (rate(http_requests_total{status=~"5.."}[1m])) / sum by (job) (rate(http_requests_total[1m]))`
3. P95 latency by service:
   - `histogram_quantile(0.95, sum by (job, le) (rate(http_request_duration_seconds_bucket[1m])))`
4. In-progress requests:
   - `sum by (job) (http_requests_inprogress)`

Additional baseline rollups used for comparison:

- Peak request rate over window
- Increase(requests) over window
- Peak p95 over window

## Baseline Results

### A) Current Snapshot (1m panel style)

- Request rate (req/s):
  - order-service: `0.488`
  - inventory-service: `0.477`
  - load-orchestrator: `0.630`
- 5xx ratio:
  - No active series returned
- P95 latency (s):
  - order-service: `0.095`
  - inventory-service: `0.095`
  - load-orchestrator: `0.400`

### B) Recent Peak (15m)

- Peak request rate (req/s):
  - order-service: `151.39`
  - inventory-service: `7.16`
  - email-service: `4.45`
  - load-orchestrator: `1.58`
- Request increase over 15m:
  - order-service: `9346.57`
  - inventory-service: `2157.06`
  - email-service: `407.68`
  - load-orchestrator: `765.64`
- Peak p95 latency (s):
  - order-service: `1.00`
  - email-service: `0.94`
  - load-orchestrator: `0.47`
  - inventory-service: `0.095`
- Peak 5xx ratio:
  - No active series returned

### C) Exact Rerun Window Anchored at Stop Time (267s)

- Request increase by service/status:
  - order-service 2xx: `8720.79`
  - inventory-service 2xx: `1843.39`
  - email-service 2xx: `261.39`
  - load-orchestrator 2xx: `218.08`
- Peak request rate (req/s):
  - order-service: `151.42`
  - inventory-service: `7.32`
  - email-service: `4.57`
  - load-orchestrator: `1.58`
- Peak p95 latency (s):
  - order-service: `1.00`
  - email-service: `0.94`
  - load-orchestrator: `0.47`
  - inventory-service: `0.095`
- Peak 5xx ratio:
  - No active series returned

## Stability Notes During Rerun

- Both email-service pods were in `CrashLoopBackOff` during this period.
- This means transport-level success (2xx) does not guarantee business-level completion.
- k6 job resources were cleaned up quickly, so Kubernetes events + Prometheus were used as authoritative evidence for this report.

## Baseline Interpretation (Before Kafka)

1. Order ingestion can spike to ~`151 req/s`.
2. Downstream email path is unstable under current architecture.
3. HTTP status metrics alone are not enough to prove end-to-end order completion.
4. In-progress metric panel currently has no data (`http_requests_inprogress` not present).

## Reusable A/B Comparison Plan (Same Conditions, With Kafka Next)

Use exactly the same load profile (`200000`, `100 VUs`, `10m`) and compare:

1. Order API ingestion stability
   - peak req/s
   - sustained req/s
2. API latency resilience
   - p95 and p99 at order-service
3. Failure isolation
   - order acceptance while email/inventory consumers are stressed
4. Delivery reliability (Kafka-specific)
   - consumer lag
   - lag recovery time
   - retry count
   - DLQ count
   - event age to completion
5. Business completion
   - accepted vs processed orders
   - time to final state

## Success Criteria for Kafka Demonstration

- Equal or higher order-service throughput at same load.
- Lower tail latency or improved stability under downstream stress.
- Fewer user-visible degradations when email/inventory has failures.
- Measurable decoupling: order intake remains stable while consumers recover asynchronously.
