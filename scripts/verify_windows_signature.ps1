param(
    [string]$ExePath = "dist\LocalMonitorAgent.exe",
    [switch]$AllowSelfSigned
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedExe = (Resolve-Path (Join-Path $projectRoot $ExePath)).Path
$signature = Get-AuthenticodeSignature $resolvedExe

if (-not $signature.SignerCertificate) {
    throw "The Windows executable does not contain an Authenticode signature."
}
if (-not $signature.TimeStamperCertificate) {
    throw "The Windows Authenticode signature is not timestamped."
}

if ($signature.Status -eq "Valid") {
    Write-Host "Windows signature is publicly trusted."
    Write-Host "Signer: $($signature.SignerCertificate.Subject)"
    exit 0
}

if (-not $AllowSelfSigned) {
    throw "Windows signature is not publicly trusted: $($signature.Status)"
}

$certificate = $signature.SignerCertificate
if ($certificate.Subject -ne $certificate.Issuer) {
    throw "The untrusted Windows signer is not self-signed: $($certificate.Subject)"
}

$now = Get-Date
if ($now -lt $certificate.NotBefore -or $now -gt $certificate.NotAfter) {
    throw "The self-signed Windows certificate is outside its validity period."
}

$ekuExtension = $certificate.Extensions |
    Where-Object { $_.Oid.Value -eq "2.5.29.37" } |
    Select-Object -First 1
$hasCodeSigningEku = $ekuExtension -and @(
    $ekuExtension.EnhancedKeyUsages |
        Where-Object { $_.Value -eq "1.3.6.1.5.5.7.3.3" }
).Count -gt 0
if (-not $hasCodeSigningEku) {
    throw "The self-signed Windows certificate is not valid for code signing."
}

# Trust only this embedded self-signed certificate in the ephemeral CI user
# store, re-run Authenticode verification, and remove it immediately afterward.
$rootStore = [System.Security.Cryptography.X509Certificates.X509Store]::new(
    "Root",
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$addedToRoot = $false
try {
    $rootStore.Open(
        [System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite
    )
    $alreadyTrusted = $rootStore.Certificates.Find(
        [System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint,
        $certificate.Thumbprint,
        $false
    ).Count -gt 0
    if (-not $alreadyTrusted) {
        $rootStore.Add($certificate)
        $addedToRoot = $true
    }

    $trustedSignature = Get-AuthenticodeSignature $resolvedExe
    if ($trustedSignature.Status -ne "Valid") {
        throw "Self-signed Authenticode verification failed after temporary trust: $($trustedSignature.Status)"
    }
}
finally {
    if ($addedToRoot) {
        $rootStore.Remove($certificate)
    }
    $rootStore.Close()
}

Write-Warning (
    "Accepted a cryptographically valid self-signed Windows certificate " +
    "because AllowSelfSigned is enabled. Windows will still warn users unless " +
    "this certificate is installed as trusted."
)
Write-Host "Signer: $($certificate.Subject)"
Write-Host "Thumbprint: $($certificate.Thumbprint)"
