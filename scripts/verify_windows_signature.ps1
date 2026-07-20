param(
    [string]$ExePath = "dist\LocalMonitorAgent.exe",
    [switch]$AllowSelfSigned,
    [ValidateRange(1, 600)]
    [int]$VerificationTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedExe = (Resolve-Path (Join-Path $projectRoot $ExePath)).Path

function Get-BoundedAuthenticodeSignature {
    param(
        [string]$FilePath,
        [int]$TimeoutSeconds
    )

    $job = Start-Job -ScriptBlock {
        param([string]$Path)

        $signature = Get-AuthenticodeSignature -FilePath $Path
        $certificate = $signature.SignerCertificate
        $timestamp = $signature.TimeStamperCertificate
        $hasCodeSigningEku = $false

        if ($certificate) {
            $ekuExtension = $certificate.Extensions |
                Where-Object { $_.Oid.Value -eq "2.5.29.37" } |
                Select-Object -First 1
            $hasCodeSigningEku = $ekuExtension -and @(
                $ekuExtension.EnhancedKeyUsages |
                    Where-Object { $_.Value -eq "1.3.6.1.5.5.7.3.3" }
            ).Count -gt 0
        }

        [pscustomobject]@{
            Status = [string]$signature.Status
            HasSigner = [bool]$certificate
            HasTimestamp = [bool]$timestamp
            Subject = if ($certificate) { $certificate.Subject } else { "" }
            Issuer = if ($certificate) { $certificate.Issuer } else { "" }
            Thumbprint = if ($certificate) { $certificate.Thumbprint } else { "" }
            NotBefore = if ($certificate) { $certificate.NotBefore } else { $null }
            NotAfter = if ($certificate) { $certificate.NotAfter } else { $null }
            HasCodeSigningEku = [bool]$hasCodeSigningEku
            CertificateRawData = if ($certificate) {
                [Convert]::ToBase64String($certificate.RawData)
            } else {
                ""
            }
        }
    } -ArgumentList $FilePath

    try {
        $completed = Wait-Job -Job $job -Timeout $TimeoutSeconds
        if (-not $completed) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            throw "Authenticode verification exceeded $TimeoutSeconds seconds."
        }
        if ($job.State -ne "Completed") {
            $details = (Receive-Job -Job $job -ErrorAction SilentlyContinue | Out-String).Trim()
            throw "Authenticode verification job ended as $($job.State). $details"
        }

        $result = Receive-Job -Job $job
        if (-not $result) {
            throw "Authenticode verification returned no result."
        }
        return $result
    }
    finally {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

$signature = Get-BoundedAuthenticodeSignature `
    -FilePath $resolvedExe `
    -TimeoutSeconds $VerificationTimeoutSeconds

if (-not $signature.HasSigner) {
    throw "The Windows executable does not contain an Authenticode signature."
}
if (-not $signature.HasTimestamp) {
    throw "The Windows Authenticode signature is not timestamped."
}

if ($signature.Status -eq "Valid") {
    Write-Host "Windows signature is publicly trusted."
    Write-Host "Signer: $($signature.Subject)"
    exit 0
}

if (-not $AllowSelfSigned) {
    throw "Windows signature is not publicly trusted: $($signature.Status)"
}

$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
    [Convert]::FromBase64String($signature.CertificateRawData)
)

if ($certificate.Subject -ne $certificate.Issuer) {
    throw "The untrusted Windows signer is not self-signed: $($certificate.Subject)"
}

$now = Get-Date
if ($now -lt $signature.NotBefore -or $now -gt $signature.NotAfter) {
    throw "The self-signed Windows certificate is outside its validity period."
}

if (-not $signature.HasCodeSigningEku) {
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

    $trustedSignature = Get-BoundedAuthenticodeSignature `
        -FilePath $resolvedExe `
        -TimeoutSeconds $VerificationTimeoutSeconds
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
Write-Host "Signer: $($signature.Subject)"
Write-Host "Thumbprint: $($signature.Thumbprint)"
