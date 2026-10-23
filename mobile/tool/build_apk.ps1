# Builds a release APK you can copy to an Android phone and install (allow "install unknown apps" for your file manager).
# Needs: JDK 17 at C:\siva\tools\jdk17, Android SDK at C:\siva\tools\android-sdk (see ../docs/open-questions.md), Flutter at C:\siva\tools\flutter.
#   powershell -ExecutionPolicy Bypass -File tool\build_apk.ps1 [-ServerUrl http://192.168.1.5:8000] [-AllAbis]
# The server address can also be changed inside the app (login screen, "Server"), so a rebuild is not needed when the PC's address changes.
param(
    [string]$ServerUrl = '',
    [switch]$AllAbis,
    [string]$OutName = 'FarmTrack-test.apk'
)
$ErrorActionPreference = 'Stop'
$mobile = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $mobile
$env:JAVA_HOME = 'C:\siva\tools\jdk17'
$env:ANDROID_HOME = 'C:\siva\tools\android-sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "C:\siva\tools\flutter\bin;$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;" + $env:PATH

if (-not $ServerUrl) {
    $ip = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -like '172.*' } |
        Select-Object -First 1 -ExpandProperty IPAddress
    $ServerUrl = "http://${ip}:8000"
}
Write-Host "Server address built in (changeable in the app): $ServerUrl"

Set-Location $mobile
& flutter config --android-sdk $env:ANDROID_HOME --jdk-dir $env:JAVA_HOME | Out-Null
$platform = if ($AllAbis) { 'android-arm,android-arm64,android-x64' } else { 'android-arm64' }   # arm64 = every phone of the last ~6 years
& flutter build apk --release --target-platform $platform --dart-define=API_BASE_URL=$ServerUrl
if ($LASTEXITCODE -ne 0) { throw "flutter build apk failed ($LASTEXITCODE)" }

$apk = Join-Path $mobile 'build\app\outputs\flutter-apk\app-release.apk'
$dist = Join-Path $repo 'dist'      # dist/ is not committed (see .gitignore)
New-Item -ItemType Directory -Force $dist | Out-Null
$out = Join-Path $dist $OutName
Copy-Item $apk $out -Force
Write-Host ''
Write-Host "APK ready: $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)" -ForegroundColor Green
