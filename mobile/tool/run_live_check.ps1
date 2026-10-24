<#
.SYNOPSIS
  Live contract check: starts the real backend OFFLINE on 127.0.0.1:8765, runs `flutter test test_live` against it, stops it.

.DESCRIPTION
  Nothing leaves this machine and the real API key is never used: every provider is set explicitly (mock LLM, no TTS, hash
  embeddings, in-memory vector store, log push, mock Zoho/IoT, CSV weather, no scheduler), the OpenAI and Google keys are set to
  empty, the database and the photo folder are in a temporary folder, and the server is started through a small launcher that
  switches the repo-root .env file off, so that file is not even read.
  The server is always stopped again (also when the tests fail or this script is interrupted).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File mobile\tool\run_live_check.ps1
  powershell -ExecutionPolicy Bypass -File mobile\tool\run_live_check.ps1 -Port 8770 -NoHints
#>
[CmdletBinding()]
param(
  [int]$Port = 8765,
  # Steer the stub disease classifier so an apple scan ends in advice (DEMO_DISEASE_HINTS, added by BACKEND-FIX).
  [string]$Hints = 'Apple=Apple___Apple_scab:0.9',
  [switch]$NoHints,
  [int]$StartTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
$mobile = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$root = (Resolve-Path (Join-Path $mobile '..')).Path
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "backend virtualenv not found: $python" }

# Is the hints setting available in this backend yet?
$hintsSupported = Select-String -Path (Join-Path $backend 'app\config.py') -Pattern 'demo_disease_hints' -Quiet
$useHints = (-not $NoHints) -and $hintsSupported
if ((-not $NoHints) -and (-not $hintsSupported)) {
  Write-Warning 'This backend has no DEMO_DISEASE_HINTS setting yet: disease results will be "not sure / expert" and the test expects that.'
}

# Another program on the port would make the test talk to something else. 8765 is the default; when it is taken (on the
# owner's PC another program holds it) and no port was asked for, the next free one is used.
function Test-PortBusy([int]$p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }
if (Test-PortBusy $Port) {
  if ($PSBoundParameters.ContainsKey('Port')) { throw "port $Port is already in use; pass another -Port" }
  $free = ($Port + 1)..($Port + 40) | Where-Object { -not (Test-PortBusy $_) } | Select-Object -First 1
  if (-not $free) { throw "no free port between $($Port + 1) and $($Port + 40)" }
  Write-Warning "port $Port is already in use by another program; using $free instead"
  $Port = $free
}

$temp = Join-Path ([IO.Path]::GetTempPath()) ('farmtrack-live-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$serverOut = Join-Path $temp 'server.out.log'
$serverErr = Join-Path $temp 'server.err.log'

# Real environment variables win over everything else; these are explicit on purpose.
$settings = [ordered]@{
  ENV = 'dev'; LLM_PROVIDER = 'mock'; OPENAI_API_KEY = ''; TTS_PROVIDER = 'null'; GOOGLE_TTS_API_KEY = ''
  EMBEDDINGS_PROVIDER = 'hash'; VECTOR_STORE = 'memory'; PUSH_PROVIDER = 'log'; ZOHO_PROVIDER = 'mock'; IOT_PROVIDER = 'mock'
  WEATHER_PROVIDER = 'csv'; CROP_ID_PROVIDER = 'stub'; DISEASE_PROVIDER = 'stub'; FCM_CREDENTIALS_FILE = ''
  DATABASE_URL = ('sqlite:///' + ((Join-Path $temp 'live.db') -replace '\\', '/'))
  STORAGE_DIR = (Join-Path $temp 'storage')
  ALERT_SCHEDULER = '0'
  DEMO_PASSWORD = 'farm1234'; OTP_LOGIN_ENABLED = 'false'   # the live login is f001 / farm1234, never an OTP
  DEMO_DISEASE_HINTS = $(if ($useHints) { $Hints } else { '' })
}
foreach ($entry in $settings.GetEnumerator()) { Set-Item -Path ("Env:" + $entry.Key) -Value $entry.Value }

# The launcher: switch the .env file off BEFORE the app reads its settings, then serve on localhost only.
$launcher = "from app.config import Settings; Settings.model_config['env_file'] = None; import uvicorn; " +
  "uvicorn.run('app.main:app', host='127.0.0.1', port=$Port, log_level='warning')"

$server = $null
$exitCode = 1
try {
  Write-Host "Starting the offline backend on http://127.0.0.1:$Port (hints: $(if ($useHints) { $Hints } else { 'off' }))"
  # Start-Process does not quote its arguments, and the launcher holds spaces: quote it once (it has no double quotes inside).
  $server = Start-Process -FilePath $python -ArgumentList ('-c "' + $launcher + '"') -WorkingDirectory $backend `
    -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru -WindowStyle Hidden

  $deadline = (Get-Date).AddSeconds($StartTimeoutSeconds)
  $healthy = $false
  while ((Get-Date) -lt $deadline) {
    if ($server.HasExited) { break }
    try {
      $answer = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
      if ($answer.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $healthy) {
    Write-Host '--- server log (last lines) ---'
    foreach ($log in @($serverOut, $serverErr)) { if (Test-Path $log) { Get-Content $log -Tail 25 } }
    throw 'the backend did not become healthy'
  }
  Write-Host 'Backend is up. Running flutter test test_live ...'

  $flutter = (Get-Command flutter -ErrorAction SilentlyContinue)
  $flutterPath = if ($flutter) { $flutter.Source } else { Join-Path $(if ($env:FARMTRACK_FLUTTER) { $env:FARMTRACK_FLUTTER } else { 'D:\tools\flutter' }) 'bin\flutter.bat' }
  Push-Location $mobile
  try {
    & $flutterPath test test_live --reporter expanded "--dart-define=LIVE_API_URL=http://127.0.0.1:$Port" "--dart-define=LIVE_HINTS=$($useHints.ToString().ToLower())"
    $exitCode = $LASTEXITCODE
  } finally { Pop-Location }
}
finally {
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    $server.WaitForExit(10000) | Out-Null
  }
  # The log of the server is kept next to the temp database when the run failed, otherwise everything is removed.
  if ($exitCode -eq 0) { Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue }
  else { Write-Host "Server logs kept in $temp" }
}

if ($exitCode -eq 0) { Write-Host 'LIVE CHECK PASSED' -ForegroundColor Green }
else { Write-Host "LIVE CHECK FAILED (exit code $exitCode)" -ForegroundColor Red }
exit $exitCode
