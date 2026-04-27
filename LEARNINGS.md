# Current Learning Notes

## Architecture and Bottlenecks

- In the current synchronous design, Order Service is the user-facing bottleneck under downstream stress.
- Root cause can still be downstream (Email/Inventory), but Order Service experiences backpressure first because it waits for downstream responses.
- Retry with exponential backoff increases per-request time and can amplify upstream saturation under heavy load.

## Load Testing Journey

- Started with local direct load and moved to in-cluster execution for more realistic behavior.
- Added Load Orchestrator service in Kubernetes to launch/stop k6 jobs and simulate controlled outages.
- Confirmed stress behavior with high failure/partial-failure patterns under constrained capacity.

## Chaos and Recovery

- Implemented outage simulation by scaling Email/Inventory deployments down and restoring after a configured duration.
- Observed expected degraded state during outage and recovery once replicas returned.

## Observability

- Added Prometheus scraping and Grafana dashboard provisioning.
- Instrumented services with Prometheus metrics endpoints.
- Learned that dashboard can stay blank when scrape targets are down or datasource UID mapping is incorrect.
- Verified target health and query output via Prometheus API before troubleshooting Grafana UI.

## Practical Ops Lessons

- Port-forward is useful for debug but not ideal as a primary high-load path.
- NodePort and in-cluster runners reduce local bottlenecks and improve test realism.
- Tooling on Windows may need path and profile fixes (k9s/k6 command resolution).

## Next Learning Targets

- Shift from synchronous orchestration to event-driven flow to isolate user latency from downstream delays.
- Add stronger resilience controls: circuit breaker, bulkhead, queue buffering, and idempotent retry strategy.
- Add richer dashboards with explicit chaos window markers and run correlation.
