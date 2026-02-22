# ============================================================
# Create Self-Signed Code Signing Certificate
# Local Monitor Agent - Windows
# ============================================================
# Run as Administrator in PowerShell

param(
    [string]$CertName = "Local Monitor Agent",
    [string]$OutputPath = "lma_cert.pfx",
    [int]$ValidYears = 10
)

Write-Host ""
Write-Host "========================================"
Write-Host " Creating Code Signing Certificate"
Write-Host "========================================"
Write-Host ""

# Note: This script uses Cert:\CurrentUser\My which does not require admin.
# If you need to install to Cert:\LocalMachine, run as Administrator instead.

Write-Host "Certificate Details:"
Write-Host ("  Name: " + $CertName)
Write-Host ("  Valid for: " + $ValidYears + " years")
Write-Host ("  Output: " + $OutputPath)
Write-Host ""

# Check if certificate already exists
if (Test-Path $OutputPath) {
    $confirm = Read-Host ("$OutputPath already exists. Overwrite? (y/n)")
    if ($confirm -ne "y") {
        Write-Host "Cancelled"
        exit 0
    }
}

try {
    Write-Host "Creating self-signed certificate..."
    Write-Host ""
    
    # Create self-signed certificate
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject ("CN=" + $CertName) `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3") `
        -FriendlyName ($CertName + " Code Signing") `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears($ValidYears) `
        -ErrorAction Stop
    
    Write-Host "[OK] Certificate created successfully"
    Write-Host ("     Thumbprint: " + $cert.Thumbprint)
    Write-Host ""
    
    # Prompt for password
    Write-Host "Enter password for certificate export (used for signing):"
    $password = Read-Host -AsSecureString -Prompt "Password"
    $confirmPassword = Read-Host -AsSecureString -Prompt "Confirm password"
    
    # Compare passwords
    $pass1 = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($password)
    )
    $pass2 = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($confirmPassword)
    )
    
    if ($pass1 -ne $pass2) {
        Write-Error "Passwords do not match"
        exit 1
    }
    
    if ([string]::IsNullOrEmpty($pass1)) {
        Write-Error "Password cannot be empty"
        exit 1
    }
    
    Write-Host ""
    Write-Host "Exporting certificate with private key..."
    
    # Export certificate with private key
    Export-PfxCertificate `
        -Cert $cert `
        -FilePath $OutputPath `
        -Password $password `
        -ErrorAction Stop | Out-Null
    
    Write-Host "[OK] Certificate exported to: $OutputPath"
    Write-Host ""
    
    # Also export public certificate
    $pubCertPath = $OutputPath -replace "\.pfx", ".cer"
    Write-Host "Exporting public certificate..."
    Export-Certificate `
        -Cert $cert `
        -FilePath $pubCertPath `
        -Type CERT `
        -Force | Out-Null
    
    Write-Host "[OK] Public certificate exported to: $pubCertPath"
    Write-Host ""
    
    # Install certificate to Trusted Root CA store (current user)
    # This allows SignTool verification to pass for self-signed certs
    Write-Host "Installing certificate to Trusted Root store..."
    try {
        $rootStore = New-Object System.Security.Cryptography.X509Certificates.X509Store(
            "Root",
            [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
        )
        $rootStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $rootStore.Add($cert)
        $rootStore.Close()
        Write-Host "[OK] Certificate added to Trusted Root (CurrentUser)"
    } catch {
        Write-Host "[WARN] Could not add to Trusted Root: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "       You may see verification warnings during signing."
    }
    Write-Host ""
    
    Write-Host "========================================"
    Write-Host " Certificate Created Successfully!"
    Write-Host "========================================"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Build the application:"
    Write-Host "     .\scripts\build_windows.bat"
    Write-Host ""
    Write-Host "  2. Sign the executable:"
    Write-Host "     .\scripts\sign_windows.bat"
    Write-Host ""
    Write-Host "  3. When prompted, enter the password you just created"
    Write-Host ""
    Write-Host "Certificate info:"
    Write-Host ("  Subject: CN=" + $CertName)
    Write-Host ("  Thumbprint: " + $cert.Thumbprint)
    Write-Host ("  Expires: " + $cert.NotAfter)
    Write-Host ""
    Write-Host ("WARNING: Keep $OutputPath safe - contains your private key!")
    Write-Host "         Do not commit it to version control."
    Write-Host ""
}
catch {
    Write-Error ("Error: " + $_.Exception.Message)
    exit 1
}
