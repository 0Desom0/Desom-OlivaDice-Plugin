param(
    [string]$AndroidSdk = "$env:LOCALAPPDATA\Android\Sdk"
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$androidJar = Join-Path $AndroidSdk 'platforms\android-35\android.jar'
$buildTools = Join-Path $AndroidSdk 'build-tools\35.0.0'
$aapt2 = Join-Path $buildTools 'aapt2.exe'
$d8 = Join-Path $buildTools 'd8.bat'
$javac = 'C:\Program Files\Java\jdk-1.8\bin\javac.exe'
$jbr = 'C:\Program Files\Android\Android Studio\jbr\bin'
$java = Join-Path $jbr 'java.exe'
$jar = Join-Path $jbr 'jar.exe'
$keytool = Join-Path $jbr 'keytool.exe'
$tempRoot = Join-Path $env:TEMP 'LanotaControlApkBuild'
$out = Join-Path $tempRoot 'out'
$source = Join-Path $tempRoot 'source'
$classes = Join-Path $out 'classes'
$dex = Join-Path $out 'dex'
$apkUnsigned = Join-Path $out 'LanotaControl-unsigned.apk'
$apkAligned = Join-Path $out 'LanotaControl-aligned.apk'
$keystorePersistent = Join-Path $root 'lanota-control.keystore'
$keystore = Join-Path $out 'lanota-control.keystore'
$apkFinalTemp = Join-Path $out 'LanotaControl.apk'
$apkFinal = Join-Path $root 'LanotaControl.apk'

foreach ($tool in @($androidJar, $aapt2, $d8, $javac, $java, $jar, $keytool)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "Missing build tool: $tool" }
}
if (Test-Path -LiteralPath $tempRoot) { Remove-Item -Recurse -Force -LiteralPath $tempRoot }
New-Item -ItemType Directory -Force -Path $classes, $dex | Out-Null
$sourceJava = Join-Path $source 'com\desom\lanotachinatokenuploader\MainActivity.java'
$sourceManifest = Join-Path $source 'AndroidManifest.xml'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sourceJava) | Out-Null
Copy-Item -Force -LiteralPath (Join-Path $root 'src\com\desom\lanotachinatokenuploader\MainActivity.java') -Destination $sourceJava
Copy-Item -Force -LiteralPath (Join-Path $root 'AndroidManifest.xml') -Destination $sourceManifest

& $javac -source 8 -target 8 -encoding UTF-8 -classpath $androidJar -d $classes $sourceJava
if ($LASTEXITCODE -ne 0) { throw 'javac failed' }
$oldJavaHome = $env:JAVA_HOME
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
& $d8 --lib $androidJar --output $dex (Get-ChildItem -LiteralPath $classes -Filter '*.class' -Recurse | Select-Object -ExpandProperty FullName)
$env:JAVA_HOME = $oldJavaHome
if ($LASTEXITCODE -ne 0) { throw 'd8 failed' }
& $aapt2 link -I $androidJar --manifest $sourceManifest --min-sdk-version 23 --target-sdk-version 35 -o $apkUnsigned
if ($LASTEXITCODE -ne 0) { throw 'aapt2 link failed' }
Copy-Item -Force (Join-Path $dex 'classes.dex') (Join-Path $out 'classes.dex')
Push-Location $out
try { & $jar uf $apkUnsigned classes.dex } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'adding dex failed' }
& (Join-Path $buildTools 'zipalign.exe') -f 4 $apkUnsigned $apkAligned
if ($LASTEXITCODE -ne 0) { throw 'zipalign failed' }
if (Test-Path -LiteralPath $keystorePersistent) {
    Copy-Item -Force -LiteralPath $keystorePersistent -Destination $keystore
} else {
    & $keytool -genkeypair -keystore $keystore -storepass lanota-module -alias lanota -keypass lanota-module -keyalg RSA -keysize 2048 -validity 3650 -dname 'CN=Lanota Control,O=Desom'
    if ($LASTEXITCODE -ne 0) { throw 'keytool failed' }
    Copy-Item -Force -LiteralPath $keystore -Destination $keystorePersistent
}
& (Join-Path $buildTools 'apksigner.bat') sign --ks $keystore --ks-pass pass:lanota-module --out $apkFinalTemp $apkAligned
if ($LASTEXITCODE -ne 0) { throw 'apksigner failed' }
& (Join-Path $buildTools 'apksigner.bat') verify --verbose $apkFinalTemp
if ($LASTEXITCODE -ne 0) { throw 'APK verification failed' }
Copy-Item -Force -LiteralPath $apkFinalTemp -Destination $apkFinal
Write-Host "APK: $apkFinal"
Write-Host "SHA256: $((Get-FileHash -Algorithm SHA256 -LiteralPath $apkFinal).Hash.ToLowerInvariant())"
