# Starts the FarmTrack backend so a phone on the SAME Wi-Fi can use it (plain http, port 8000).
#   - real crop + disease models from backend\storage\models (copied, no download), CPU, first scan loads them (~15 s)
#   - no cloud calls: mock advice composer (validated templates), no OpenAI, no Google TTS (the phone speaks)
#   - demo clock 12 May 2026 (apple season), demo farmers f001..f050, password farm1234
# Run:  powershell -ExecutionPolicy Bypass -File scripts/start_backend_for_phone.ps1      (stop with Ctrl+C)
# Windows asks once whether Python may accept network connections: choose "Allow" (private networks).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # the project folder (this script lives in scripts/)
$backend = Join-Path $root 'backend'
# A separate copy of the Python interpreter (C:\siva\tools\python313, a plain copy of the installed Python 3.13): the Windows
# firewall of this laptop has a Block rule for the installed python.exe, and rules match the program's path. The packages come
# from the backend's venv and from the torch venv (data\model_test\.venv) through PYTHONPATH.
$py = 'C:\siva\tools\python313\python.exe'
if (-not (Test-Path $py)) { $py = Join-Path $root 'data\model_test\.venv\Scripts\python.exe'; Write-Warning 'python copy not found: using the venv python (the firewall may block it)' }
$env:PYTHONPATH = (Join-Path $backend '.venv\Lib\site-packages') + ';' + (Join-Path $root 'data\model_test\.venv\Lib\site-packages')
$env:ENV = 'dev'
$env:LLM_PROVIDER = 'mock'
$env:OPENAI_API_KEY = ''
$env:TTS_PROVIDER = 'null'
$env:GOOGLE_TTS_API_KEY = ''
$env:EMBEDDINGS_PROVIDER = 'hash'
$env:VECTOR_STORE = 'memory'
$env:CROP_ID_PROVIDER = 'model'
$env:DISEASE_PROVIDER = 'model'
$env:STORAGE_DIR = Join-Path $backend 'storage'
$env:PUSH_PROVIDER = 'log'
$env:ZOHO_PROVIDER = 'mock'
$env:IOT_PROVIDER = 'mock'
$env:WEATHER_PROVIDER = 'csv'
$env:OTP_LOGIN_ENABLED = 'false'
$env:HF_HUB_OFFLINE = '1'          # the weights are already in storage\models; never go to the internet

$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress
Write-Host ''
Write-Host 'In the app, on the login screen, tap "Server" and type one of these (phone and PC on the same Wi-Fi):' -ForegroundColor Green
foreach ($ip in $ips) { Write-Host "    http://${ip}:8000" -ForegroundColor Green }
Write-Host 'Login: user name f001, password farm1234' -ForegroundColor Green
Write-Host ''
Set-Location $backend
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
