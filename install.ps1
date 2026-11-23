$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv --without-pip .venv
if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment' }
python -m pip --python .\.venv\Scripts\python.exe install -r requirements-test.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; check Python and pip >= 22.3' }
.\.venv\Scripts\python.exe -m mom_basis init
if ($LASTEXITCODE -ne 0) { throw 'State initialization failed' }
Write-Host 'Ready. Run .\start_offline.ps1 or .\start_live.ps1'
