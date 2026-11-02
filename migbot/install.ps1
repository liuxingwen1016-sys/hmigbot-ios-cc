#Requires -Version 5.1
# Native Windows entry point for the packaged CC installer (also used by OTA).
param(
    [Alias('Project')][string]$Target = (Get-Location).Path,
    [ValidateSet('native','arch','1to1')][string]$MigrationHost = 'native',
    [ValidateSet('project','user')][string]$Scope = 'project',
    [string]$Lang = ''
)
$ErrorActionPreference = 'Stop'
$python = $null
  foreach ($candidate in @('python', 'python3')) {
    $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue
    if ($command) {
      try { & $command.Source -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' 2>$null } catch { continue }
      if ($LASTEXITCODE -eq 0) { $python = $command.Source; break }
    }
  }
  if (-not $python) { throw 'Python 3.9 or newer is required to install this package' }
$installArgs = @('-u', '-X', 'utf8', (Join-Path $PSScriptRoot 'scripts/migbot-install.py'),
    '--repo-root', $PSScriptRoot, '--project', $Target, '--host', $MigrationHost, '--scope', $Scope, '--yes')
if ($Lang) { $installArgs += @('--lang', $Lang) }
& $python @installArgs
exit $LASTEXITCODE
