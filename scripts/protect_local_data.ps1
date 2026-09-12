$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$dataRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot 'data'))
if (-not $dataRoot.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Unsafe data directory'}
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
# Windows PowerShell cannot always load Microsoft.PowerShell.Security when it
# inherits a PowerShell 7 PSModulePath, as hosted Windows CI does, and Get-Acl
# then fails even though icacls works. Restore the machine default for this
# process, and fall back to the .NET API, so the DACL is always verified.
$machineModules=[Environment]::GetEnvironmentVariable('PSModulePath','Machine')
if ($machineModules) {$env:PSModulePath=$machineModules}
function Get-DataAccessRules([string]$path) {
    try {return (Get-Acl -LiteralPath $path).Access}
    catch {return (New-Object System.IO.DirectoryInfo $path).GetAccessControl().Access}
}
$currentSid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed=@($currentSid,'S-1-5-18','S-1-5-32-544')
# icacls changes the DACL only, avoiding SACL/owner privilege requirements in PS 5.1.
& icacls.exe $dataRoot /inheritance:r /grant:r "*${currentSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) {throw 'Could not protect data permissions'}
foreach ($rule in (Get-DataAccessRules $dataRoot)) {
    $sid=$rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($sid -notin $allowed) {
        & icacls.exe $dataRoot /remove "*$sid" | Out-Null
        if ($LASTEXITCODE -ne 0) {throw 'Could not remove an unwanted data access rule'}
    }
}
Write-Output 'Local data permissions protected for current account, SYSTEM and Administrators.'
