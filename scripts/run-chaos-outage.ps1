param(
    [string]$Namespace = "kafka-lab",
    [ValidateSet("email-service", "inventory-service")]
    [string]$TargetService = "email-service",
    [int]$OutageSeconds = 90,
    [int]$RecoveryReplicas = 2
)

$ErrorActionPreference = "Stop"

Write-Host "Scaling $TargetService to 0 replicas in namespace $Namespace..."
kubectl -n $Namespace scale deployment $TargetService --replicas=0

Write-Host "Outage active for $OutageSeconds seconds. Keep load test running in another terminal."
for ($remaining = $OutageSeconds; $remaining -gt 0; $remaining--) {
    if ($remaining % 10 -eq 0 -or $remaining -le 5) {
        Write-Host "$remaining seconds remaining..."
    }
    Start-Sleep -Seconds 1
}

Write-Host "Restoring $TargetService to $RecoveryReplicas replicas..."
kubectl -n $Namespace scale deployment $TargetService --replicas=$RecoveryReplicas
kubectl -n $Namespace rollout status deployment/$TargetService --timeout=240s

Write-Host "$TargetService recovered."
