param(
    [ValidateSet("email")]
    [string]$Service = "email",
    [bool]$Enabled = $true,
    [ValidateSet("error", "delay")]
    [string]$Mode = "error",
    [double]$ErrorRate = 1.0,
    [double]$DelaySeconds = 0,
    [string]$BaseHost = "http://localhost"
)

$uri = "$BaseHost`:8001/failure-mode"

$payload = @{
    enabled = $Enabled
    mode = $Mode
    error_rate = $ErrorRate
    delay_seconds = $DelaySeconds
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $payload
Write-Host "Updated failure mode for email via $uri"
