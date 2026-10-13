$root = "C:\Projects\aircontrol"
$zip = "C:\Users\Richu\Downloads\AirSketch_V14_recognition_diagnostics_patch.zip"
$tmp = Join-Path $root "_v14_patch_tmp"

if (!(Test-Path $zip)) {
    Write-Host "PATCH ZIP NOT FOUND: $zip" -ForegroundColor Red
    return
}

if (Test-Path $tmp) {
    Remove-Item $tmp -Recurse -Force
}

Expand-Archive -Path $zip -DestinationPath $tmp -Force

$files = @(Get-ChildItem $tmp -Recurse -File)
$expected = @("apply_v14_internal.ps1")

if ($files.Count -ne $expected.Count) {
    Write-Host "Unexpected file count in patch ZIP." -ForegroundColor Red
    $files | ForEach-Object { Write-Host $_.FullName }
    Remove-Item $tmp -Recurse -Force
    return
}

$names = @($files | ForEach-Object { $_.Name })

foreach ($name in $expected) {
    if ($names -notcontains $name) {
        Write-Host "Missing expected patch file: $name" -ForegroundColor Red
        Remove-Item $tmp -Recurse -Force
        return
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $tmp "apply_v14_internal.ps1")

$rc = $LASTEXITCODE

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

if ($rc -ne 0) {
    Write-Host "V14 patch script returned code $rc." -ForegroundColor Red
    return
}

Remove-Item (Join-Path $root "backend\sketch\__pycache__") `
    -Recurse -Force -ErrorAction SilentlyContinue

Remove-Item (Join-Path $root "backend\tests\__pycache__") `
    -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "V14 PATCH APPLIED SUCCESSFULLY." -ForegroundColor Green
Write-Host ""
Write-Host "Run:"
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  pytest -q backend\tests\test_sketch_mouse_mode.py"
Write-Host "  pytest -q"
