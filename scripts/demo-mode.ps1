[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "email-before-keda",
        "email-after-keda",
        "stock-before-redis",
        "stock-after-redis"
    )]
    [string]$Mode,

    [string]$Namespace = "kafka-lab",
    [int]$RolloutTimeoutSeconds = 180,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Section([string]$Message) {
    Write-Host ""
    Write-Host "== $Message =="
}

function Invoke-Kubectl {
    param(
        [string[]]$KubectlArgs,
        [string]$InputText = "",
        [switch]$AllowFailure
    )

    if ($DryRun) {
        Write-Host ("DRYRUN: kubectl " + ($KubectlArgs -join " "))
        if ($InputText) {
            Write-Host $InputText
        }
        return
    }

    if ($InputText) {
        $InputText | & kubectl @KubectlArgs
    } else {
        & kubectl @KubectlArgs
    }

    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "kubectl failed: $($KubectlArgs -join ' ')"
    }
}

function Test-KedaCrd {
    & kubectl get crd scaledobjects.keda.sh -o name 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Ensure-KedaInstalled {
    if (Test-KedaCrd) {
        return
    }

    Write-Section "Installing KEDA"
    Invoke-Kubectl -KubectlArgs @(
        "apply",
        "-f",
        "https://github.com/kedacore/keda/releases/download/v2.13.0/keda-2.13.0.yaml"
    ) -AllowFailure

    if (-not (Test-KedaCrd)) {
        throw "KEDA install failed (ScaledObjects CRD missing)"
    }

    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/keda-operator",
        "-n",
        "keda",
        "--timeout=${RolloutTimeoutSeconds}s"
    )
    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/keda-metrics-apiserver",
        "-n",
        "keda",
        "--timeout=${RolloutTimeoutSeconds}s"
    )
}

function Apply-EmailScaledObject {
    $bootstrap = "kafka.$Namespace.svc.cluster.local:9092"
    $yaml = @"
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: email-service-keda
  namespace: $Namespace
spec:
  scaleTargetRef:
    name: email-service
    apiVersion: apps/v1
    kind: Deployment
  minReplicaCount: 2
  maxReplicaCount: 16
  pollingInterval: 30
  cooldownPeriod: 300
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: $bootstrap
        consumerGroup: email-service-consumer
        topic: orders.created
        lagThreshold: "10"
        offsetResetPolicy: latest
        allowIdleConsumers: "false"
"@

    Invoke-Kubectl -KubectlArgs @("apply", "-f", "-") -InputText $yaml
}

function Apply-EmailHpa {
    $yaml = @"
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: email-service-hpa
  namespace: $Namespace
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: email-service
  minReplicas: 2
  maxReplicas: 8
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      selectPolicy: Max
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 60
      selectPolicy: Min
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
"@

    Invoke-Kubectl -KubectlArgs @("apply", "-f", "-") -InputText $yaml
}

function Enable-EmailKeda {
    Write-Section "Enable KEDA for email-service"
    Ensure-KedaInstalled

    Invoke-Kubectl -KubectlArgs @(
        "delete",
        "hpa",
        "email-service-hpa",
        "-n",
        $Namespace,
        "--ignore-not-found"
    )

    Apply-EmailScaledObject

    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/email-service",
        "-n",
        $Namespace,
        "--timeout=${RolloutTimeoutSeconds}s"
    )
}

function Disable-EmailKeda {
    Write-Section "Disable KEDA for email-service"

    if (Test-KedaCrd) {
        Invoke-Kubectl -KubectlArgs @(
            "delete",
            "scaledobject",
            "email-service-keda",
            "-n",
            $Namespace,
            "--ignore-not-found"
        )
    } else {
        Write-Host "KEDA CRD not found; skipping scaledobject delete"
    }
    Invoke-Kubectl -KubectlArgs @(
        "delete",
        "hpa",
        "keda-hpa-email-service-keda",
        "-n",
        $Namespace,
        "--ignore-not-found"
    )

    Apply-EmailHpa

    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/email-service",
        "-n",
        $Namespace,
        "--timeout=${RolloutTimeoutSeconds}s"
    )
}

function Set-RedisState([bool]$Enabled) {
    $value = if ($Enabled) { "true" } else { "false" }
    $label = if ($Enabled) { "Enable" } else { "Disable" }

    Write-Section "$label Redis in order-service and inventory-service"

    Invoke-Kubectl -KubectlArgs @(
        "set",
        "env",
        "deployment/order-service",
        "-n",
        $Namespace,
        "REDIS_ENABLED=$value",
        "REDIS_PREFER_CACHE=$value"
    )
    Invoke-Kubectl -KubectlArgs @(
        "set",
        "env",
        "deployment/inventory-service",
        "-n",
        $Namespace,
        "REDIS_ENABLED=$value",
        "REDIS_PREFER_CACHE=$value"
    )

    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/order-service",
        "-n",
        $Namespace,
        "--timeout=${RolloutTimeoutSeconds}s"
    )
    Invoke-Kubectl -KubectlArgs @(
        "rollout",
        "status",
        "deployment/inventory-service",
        "-n",
        $Namespace,
        "--timeout=${RolloutTimeoutSeconds}s"
    )
}

switch ($Mode) {
    "email-before-keda" { Disable-EmailKeda }
    "email-after-keda" { Enable-EmailKeda }
    "stock-before-redis" { Set-RedisState -Enabled $false }
    "stock-after-redis" { Set-RedisState -Enabled $true }
}
