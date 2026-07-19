param(
    [string]$ExePath = "dist\LocalMonitorAgent.exe",
    [string]$PfxPath = "lma_cert.pfx",
    [string]$CertificateThumbprint = "",
    [switch]$AllowUntrustedDevelopmentCertificate
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedExe = (Resolve-Path (Join-Path $projectRoot $ExePath)).Path
$importedThumbprints = @()

$signtool = Get-ChildItem -Path "C:\Program Files (x86)\Windows Kits" `
    -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '[\\/]x64[\\/]signtool\.exe$' } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $signtool) {
    throw "SignTool was not found. Install the Windows SDK."
}

try {
    if ($CertificateThumbprint) {
        $thumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()
        $certificate = Get-Item "Cert:\CurrentUser\My\$thumbprint" -ErrorAction Stop
        if (-not $certificate.HasPrivateKey) {
            throw "The selected certificate has no accessible private key."
        }
    }
    else {
        $resolvedPfx = (Resolve-Path (Join-Path $projectRoot $PfxPath)).Path
        $before = @(Get-ChildItem Cert:\CurrentUser\My | ForEach-Object Thumbprint)
        $password = Read-Host "PFX password" -AsSecureString
        $imported = @(Import-PfxCertificate -FilePath $resolvedPfx `
            -CertStoreLocation Cert:\CurrentUser\My -Password $password)
        $certificate = $imported |
            Where-Object { $_.HasPrivateKey } |
            Select-Object -First 1
        if (-not $certificate) {
            throw "The PFX did not contain an accessible signing private key."
        }
        $thumbprint = $certificate.Thumbprint
        $importedThumbprints = @($imported |
            Where-Object { $_.Thumbprint -notin $before } |
            ForEach-Object Thumbprint)
    }

    $selfSigned = $certificate.Subject -eq $certificate.Issuer
    if ($selfSigned -and -not $AllowUntrustedDevelopmentCertificate) {
        throw "Refusing a self-signed certificate for a trusted release. Use -AllowUntrustedDevelopmentCertificate only for managed test devices."
    }

    & $signtool.FullName sign /sha1 $thumbprint /s My /fd SHA256 `
        /tr http://timestamp.digicert.com /td SHA256 `
        /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA" `
        $resolvedExe
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool signing failed."
    }

    $signature = Get-AuthenticodeSignature $resolvedExe
    if (-not $signature.SignerCertificate) {
        throw "The executable does not contain an Authenticode signature."
    }
    if ($signature.Status -ne "Valid" -and -not $AllowUntrustedDevelopmentCertificate) {
        throw "The signature is not trusted: $($signature.Status)."
    }

    Write-Host "Signed: $resolvedExe"
    Write-Host "Status: $($signature.Status)"
    Write-Host "Signer: $($signature.SignerCertificate.Subject)"
    Write-Host "Timestamped: $([bool]$signature.TimeStamperCertificate)"
    Write-Host "SHA256: $((Get-FileHash $resolvedExe -Algorithm SHA256).Hash)"
}
finally {
    foreach ($importedThumbprint in $importedThumbprints) {
        Remove-Item "Cert:\CurrentUser\My\$importedThumbprint" -Force `
            -ErrorAction SilentlyContinue
    }
}
