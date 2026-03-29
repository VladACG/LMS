$ErrorActionPreference = 'Stop'

function Invoke-Step {
    param (
        [string]$Title,
        [scriptblock]$Action
    )

    Write-Host $Title
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Title (exit code $LASTEXITCODE)"
    }
}

Invoke-Step '[1/4] Backend tests' {
    Set-Location "$PSScriptRoot\..\backend"
    ..\.venv\Scripts\python.exe -m pytest
}

Invoke-Step '[2/4] Backend load smoke' {
    Set-Location "$PSScriptRoot\.."
    $env:PYTHONPATH = 'backend'
    .\.venv\Scripts\python.exe tests/load/backend_smoke.py
}

Invoke-Step '[3/4] Frontend build' {
    Set-Location "$PSScriptRoot\..\frontend"
    npm.cmd run build
}

Invoke-Step '[4/4] Frontend tests' {
    Set-Location "$PSScriptRoot\..\frontend"
    npm.cmd run test
}

Write-Host 'All checks passed.'
