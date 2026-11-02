#Requires -Version 5.1
# Only launch plumbing lives here; source selection, validation and installation
# are implemented by a2h. Copy the executable so Windows can replace the old one.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$temp = $null
try {
    $arch = if ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64' -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $source = @((Join-Path $PSScriptRoot 'a2h.exe'), (Join-Path $PSScriptRoot "a2h-windows-$arch.exe")) |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $source) { throw 'a2h runtime is missing; reinstall the package' }
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $temp = Join-Path $tempBase ('a2h-ota-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temp | Out-Null
    $exe = Join-Path $temp 'a2h.exe'
    Copy-Item -LiteralPath $source -Destination $exe
    $updateArgs = @('update-check', '--root', $root, '--product', 'hmigbot-cc')
    if ($CheckOnly) { $updateArgs += '--check-only' }
    # Inherit stderr for live progress. ProcessStartInfo avoids PowerShell 5.1
    # treating native stderr as terminating errors under ErrorActionPreference=Stop.
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $exe
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.CreateNoWindow = $true
    $start.Arguments = (($updateArgs | ForEach-Object {
        '"' + (($_ -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
    }) -join ' ')
    $process = [System.Diagnostics.Process]::Start($start)
    try {
        $output = $process.StandardOutput.ReadToEnd()
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } finally { $process.Dispose() }
    if ($exitCode -ne 0) { throw 'a2h update-check failed; install a package containing the OTA runtime' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if (-not $result.status) { throw 'a2h returned no update status' }
    $result | ConvertTo-Json -Compress
} catch {
    @{ status = 'error'; detail = $_.Exception.Message } | ConvertTo-Json -Compress
} finally {
    if ($temp) {
        $resolved = [IO.Path]::GetFullPath($temp)
        $boundary = $tempBase.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        if ($resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetFileName($resolved) -match '^a2h-ota-[0-9a-f]{32}$') {
            Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
exit 0
