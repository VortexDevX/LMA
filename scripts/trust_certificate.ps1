# Trust the self-signed certificate by adding it to CurrentUser Trusted Root store
param(
    [string]$CertPath = "lma_cert.cer"
)

if (-not (Test-Path $CertPath)) {
    Write-Error "Certificate not found: $CertPath"
    exit 1
}

Write-Host ""
Write-Host "Adding certificate to Trusted Root store..."

$certObj = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
    (Resolve-Path $CertPath).Path
)

$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)

$store.Open(
    [System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite
)

$store.Add($certObj)
$store.Close()

Write-Host "[OK] Certificate added to Trusted Root (CurrentUser)"
Write-Host "     Subject: $($certObj.Subject)"
Write-Host "     Thumbprint: $($certObj.Thumbprint)"
Write-Host ""
Write-Host "SignTool verification should now pass for this certificate."
Write-Host ""
