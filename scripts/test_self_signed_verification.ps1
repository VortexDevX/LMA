param(
    [string]$SourceExe = "dist\LocalMonitorAgent.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedSource = (Resolve-Path (Join-Path $projectRoot $SourceExe)).Path
$testDirectory = Join-Path $projectRoot ".signature-test"
$testExe = Join-Path $testDirectory "LocalMonitorAgent-selfsigned.exe"
$certificate = $null

try {
    New-Item -ItemType Directory -Path $testDirectory -Force | Out-Null
    Copy-Item -LiteralPath $resolvedSource -Destination $testExe -Force
    $certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=LMA CI Self-Signed Verification Test" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddDays(2)

    $signature = Set-AuthenticodeSignature `
        -FilePath $testExe `
        -Certificate $certificate `
        -HashAlgorithm SHA256 `
        -TimestampServer "http://timestamp.digicert.com"
    Write-Host "Before temporary trust: $($signature.Status)"
    if ($signature.Status -notin @("UnknownError", "NotTrusted")) {
        throw "Expected an untrusted test signature, got $($signature.Status)."
    }

    $rejectedWithoutOptIn = $false
    try {
        & (Join-Path $PSScriptRoot "verify_windows_signature.ps1") `
            -ExePath ".signature-test\LocalMonitorAgent-selfsigned.exe"
    }
    catch {
        if ($_.Exception.Message -notlike "Windows signature is not publicly trusted:*") {
            throw
        }
        $rejectedWithoutOptIn = $true
        Write-Host "PASS self-signed signature is rejected without explicit opt-in"
    }
    if (-not $rejectedWithoutOptIn) {
        throw "The self-signed signature was accepted without explicit opt-in."
    }

    & (Join-Path $PSScriptRoot "verify_windows_signature.ps1") `
        -ExePath ".signature-test\LocalMonitorAgent-selfsigned.exe" `
        -AllowSelfSigned

    $remainingRootCertificates = @(
        Get-ChildItem Cert:\CurrentUser\Root |
            Where-Object Thumbprint -eq $certificate.Thumbprint
    ).Count
    if ($remainingRootCertificates -ne 0) {
        throw "The temporary root certificate was not removed."
    }
    Write-Host "PASS self-signed verification and root-store cleanup"
}
finally {
    if ($certificate) {
        Remove-Item "Cert:\CurrentUser\My\$($certificate.Thumbprint)" `
            -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $testExe -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testDirectory -Force -ErrorAction SilentlyContinue
}
