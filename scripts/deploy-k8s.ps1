param(
    [string]$Namespace = "kafka-lab"
)

$ErrorActionPreference = "Stop"

Write-Host "Building service images..."
docker build -t kafka-order-service:latest .\order-service
docker build -t kafka-email-service:latest .\email-service
docker build -t kafka-inventory-service:latest .\inventory-service
docker build -t kafka-load-orchestrator:latest .\load-orchestrator

Write-Host "Applying Kubernetes manifests..."
kubectl apply -k .\k8s

Write-Host "Waiting for rollouts..."
kubectl -n $Namespace rollout status deployment/order-service --timeout=240s
kubectl -n $Namespace rollout status deployment/email-service --timeout=240s
kubectl -n $Namespace rollout status deployment/inventory-service --timeout=240s
kubectl -n $Namespace rollout status deployment/load-orchestrator --timeout=240s
kubectl -n $Namespace rollout status deployment/prometheus --timeout=240s
kubectl -n $Namespace rollout status deployment/grafana --timeout=240s

Write-Host "Deploy complete."
Write-Host "Use this command to expose Order Service locally:"
Write-Host "kubectl -n $Namespace port-forward svc/order-service 8000:8000"
Write-Host "Load Orchestrator UI: http://localhost:30081"
Write-Host "Prometheus UI: http://localhost:30090"
Write-Host "Grafana UI: http://localhost:30300 (admin/admin)"
