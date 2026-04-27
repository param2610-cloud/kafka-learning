param(
    [ValidateSet("email", "inventory")]
    [string]$Service = "email",
    [bool]$Enabled = $true,
    [ValidateSet("error", "delay")]
    [string]$Mode = "error",
    [double]$ErrorRate = 1.0,
    [double]$DelaySeconds = 0,
    [string]$BaseHost = "http://localhost"
)

$port = if ($Service -eq "email") { 8001 } else { 8002 }
$uri = "$BaseHost`:$port/failure-mode"

$payload = @{
    enabled = $Enabled
    mode = $Mode
    error_rate = $ErrorRate
    delay_seconds = $DelaySeconds
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $payload
Write-Host "Updated failure mode for $Service via $uri"
