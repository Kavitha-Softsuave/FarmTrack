# Builds an APK you can copy to an Android phone and install (allow "install unknown apps" for your file manager).
# Needs JDK 17, the Android SDK and Flutter. Folder lookup (first that is set wins): the parameters, then the environment
# variables FARMTRACK_JDK, FARMTRACK_ANDROID_SDK, FARMTRACK_FLUTTER, then FARMTRACK_TOOLS (parent folder, default D:\tools)
# with jdk17, android-sdk and flutter inside it. See ../docs/dev-setup.md.
#   powershell -ExecutionPolicy Bypass -File tool\build_apk.ps1 [-ServerUrl http://192.168.1.5:8000] [-AllAbis] [-Debug]
# The server address can also be changed inside the app (login screen, "Server"), so a rebuild is not needed when the PC's address changes.
param(
    [string]$ServerUrl = '',
    [switch]$AllAbis,
    [switch]$Debug,
    [string]$OutName = 'FarmTrack-test.apk',
    [string]$ToolsDir = $(if ($env:FARMTRACK_TOOLS) { $env:FARMTRACK_TOOLS } else { 'D:\tools' }),
    [string]$JdkDir = $(if ($env:FARMTRACK_JDK) { $env:FARMTRACK_JDK } else { Join-Path $ToolsDir 'jdk17' }),
    [string]$AndroidSdkDir = $(if ($env:FARMTRACK_ANDROID_SDK) { $env:FARMTRACK_ANDROID_SDK } else { Join-Path $ToolsDir 'android-sdk' }),
    [string]$FlutterDir = $(if ($env:FARMTRACK_FLUTTER) { $env:FARMTRACK_FLUTTER } else { Join-Path $ToolsDir 'flutter' })
)
$ErrorActionPreference = 'Stop'
$mobile = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $mobile
foreach ($d in @($JdkDir, $AndroidSdkDir, $FlutterDir)) {
    if (-not (Test-Path $d)) { throw "Tool folder not found: $d (set FARMTRACK_TOOLS, or FARMTRACK_JDK / FARMTRACK_ANDROID_SDK / FARMTRACK_FLUTTER)" }
}
$env:JAVA_HOME = $JdkDir
$env:ANDROID_HOME = $AndroidSdkDir
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$FlutterDir\bin;$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;" + $env:PATH

if (-not $ServerUrl) {
    $ip = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -like '172.*' } |
        Select-Object -First 1 -ExpandProperty IPAddress
    $ServerUrl = "http://${ip}:8000"
}
Write-Host "Server address built in (changeable in the app): $ServerUrl"

Set-Location $mobile
& flutter config --android-sdk $env:ANDROID_HOME --jdk-dir $env:JAVA_HOME | Out-Null
$platform = if ($AllAbis) { 'android-arm,android-arm64,android-x64' } else { 'android-arm64' }   # arm64 = every phone of the last ~6 years
$mode = if ($Debug) { 'debug' } else { 'release' }
& flutter build apk --$mode --target-platform $platform --dart-define=API_BASE_URL=$ServerUrl
if ($LASTEXITCODE -ne 0) { throw "flutter build apk failed ($LASTEXITCODE)" }

$apk = Join-Path $mobile "build\app\outputs\flutter-apk\app-$mode.apk"
$dist = Join-Path $repo 'dist'      # dist/ is not committed (see .gitignore)
New-Item -ItemType Directory -Force $dist | Out-Null
$out = Join-Path $dist $OutName
Copy-Item $apk $out -Force
Write-Host ''
Write-Host "APK ready: $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)" -ForegroundColor Green
