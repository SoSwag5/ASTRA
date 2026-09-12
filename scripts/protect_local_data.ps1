$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path $PSScriptRoot -Parent
$dataRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'data'))

if (-not $dataRoot.StartsWith(
    $projectRoot + [System.IO.Path]::DirectorySeparatorChar,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'Unsafe data directory.'
}

# Ensure the data directory exists.
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null

# Get the EXISTING ACL instead of constructing a fresh security descriptor.
# This avoids unnecessarily touching ownership/auditing information.
$acl = Get-Acl -LiteralPath $dataRoot

# Disable inherited permissions and discard inherited access rules.
$acl.SetAccessRuleProtection($true, $false)

# Remove any existing explicit access rules.
foreach ($rule in @($acl.Access)) {
    $acl.RemoveAccessRuleSpecific($rule)
}

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User

$inheritance = (
    [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
    [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
)

$propagation = [System.Security.AccessControl.PropagationFlags]::None
$allow = [System.Security.AccessControl.AccessControlType]::Allow
$fullControl = [System.Security.AccessControl.FileSystemRights]::FullControl

# Allow:
# - Current Windows user
# - SYSTEM
# - BUILTIN\Administrators
foreach ($sidText in @(
    $currentIdentity.Value,
    'S-1-5-18',
    'S-1-5-32-544'
)) {
    $sid = [System.Security.Principal.SecurityIdentifier]::new($sidText)

    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $sid,
        $fullControl,
        $inheritance,
        $propagation,
        $allow
    )

    $acl.AddAccessRule($rule)
}

# Apply the access permissions.
$directory = [System.IO.DirectoryInfo]::new($dataRoot)
[System.IO.FileSystemAclExtensions]::SetAccessControl($directory, $acl)

Write-Output 'Local data directory permissions protected.'
Write-Output 'Allowed: current Windows account, SYSTEM, and Administrators.'