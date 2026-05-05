param(
    [string]$Namespace = "kafka-lab"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
Set-Location $repoRoot

$tag = Get-Date -Format "yyyyMMddHHmmss"
$images = @(
    @{
        Deployment = "order-service"
        Container = "order-service"
        Name = "kafka-order-service"
        Context = "order-service"
    },
    @{
        Deployment = "email-service"
        Container = "email-service"
        Name = "kafka-email-service"
        Context = "email-service"
    },
    @{
        Deployment = "inventory-service"
        Container = "inventory-service"
        Name = "kafka-inventory-service"
        Context = "inventory-service"
    },
    @{
        Deployment = "load-orchestrator"
        Container = "load-orchestrator"
        Name = "kafka-load-orchestrator"
        Context = "load-orchestrator"
    }
)

Write-Host "Building service images with tag $tag..."
foreach ($image in $images) {
    $image.Ref = "$($image.Name):$tag"
    docker build --pull -t $image.Ref ".\$($image.Context)"
}

$currentContext = kubectl config current-context
Write-Host "Current kubectl context: $currentContext"
if ($currentContext -like "kind-*") {
    $kindClusterName = $currentContext.Substring(5)
    Write-Host "Loading images into kind cluster '$kindClusterName'..."
    foreach ($image in $images) {
        kind load docker-image $image.Ref --name $kindClusterName
    }
}
elseif ($currentContext -eq "minikube") {
    Write-Host "Loading images into minikube..."
    foreach ($image in $images) {
        minikube image load $image.Ref
    }
}
elseif ($currentContext -eq "docker-desktop") {
    Write-Host "Using Docker Desktop Kubernetes; local Docker images are available to the cluster."
    Write-Host "No image load step required - deployments will reference the locally built image refs."
}
else {
    # Non-local clusters must be able to pull the built images. Support a simple registry push workflow.
    $registry = $env:DOCKER_REGISTRY
    if (-not $registry) {
        Write-Error "Cluster context '$currentContext' is not kind/minikube and DOCKER_REGISTRY is not set."
        Write-Error "Either use a local kind/minikube cluster, or set DOCKER_REGISTRY (e.g. myregistry.example.com/myrepo) and ensure 'docker push' can authenticate."
        exit 1
    }

    Write-Host "Tagging and pushing images to registry '$registry'..."
    foreach ($image in $images) {
        $fullRef = "$registry/$($image.Name):$tag"
        docker tag $image.Ref $fullRef
        docker push $fullRef
        # update the ref used later when updating deployments
        $image.Ref = $fullRef
    }
}

Write-Host "Applying Kubernetes manifests..."
kubectl apply -k .\k8s

Write-Host "Waiting for Kafka rollout..."
kubectl -n $Namespace rollout status deployment/kafka --timeout=240s

Write-Host "Ensuring Kafka topic 'orders.created' exists..."
$kafkaPod = kubectl -n $Namespace get pods -l app=kafka -o jsonpath="{.items[0].metadata.name}"
if (-not $kafkaPod) {
    throw "Kafka pod not found in namespace '$Namespace'."
}
kubectl -n $Namespace exec $kafkaPod -- /opt/kafka/bin/kafka-topics.sh `
    --bootstrap-server localhost:9092 `
    --create `
    --if-not-exists `
    --topic orders.created `
    --partitions 3 `
    --replication-factor 1

Write-Host "Updating deployments to use freshly built image tags..."
foreach ($image in $images) {
    kubectl -n $Namespace set image "deployment/$($image.Deployment)" "$($image.Container)=$($image.Ref)"
}

Write-Host "Waiting for rollouts..."
kubectl -n $Namespace rollout status deployment/kafka --timeout=240s
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
