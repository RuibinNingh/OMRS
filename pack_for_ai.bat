@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Package this project for AI-assisted editing without running any git command.
chcp 65001 >nul

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

for %%I in ("%ROOT%") do set "PROJECT_NAME=%%~nxI"

for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"

set "OUT_DIR=%ROOT%\_ai_packages"
set "STAGE=%TEMP%\omrs_ai_pack_%STAMP%"
set "ZIP_FILE=%OUT_DIR%\%PROJECT_NAME%-ai-%STAMP%.zip"

if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%" >nul 2>nul
mkdir "%OUT_DIR%" >nul 2>nul

echo Packaging project:
echo   %ROOT%
echo.
echo Output:
echo   %ZIP_FILE%
echo.

rem Keep AI\logs in the package: it is part of the AI collaboration context.
robocopy "%ROOT%" "%STAGE%" /E /R:1 /W:1 ^
  /XD ".git" ".git-history-backup*" ".playwright-mcp" "__pycache__" ".pytest_cache" "omrs_work" "_ai_packages" ^
  /XF "*.pyc" "*.pyo" "*.pyd" "*.log" "*.tmp" "*.zip" "Thumbs.db" "desktop.ini" >nul

if errorlevel 8 (
  echo.
  echo Robocopy failed. Package was not created.
  rmdir /s /q "%STAGE%" >nul 2>nul
  exit /b 1
)

rem Remove excluded folders from staging
if exist "%STAGE%\错题" rmdir /s /q "%STAGE%\错题"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$stage = $env:STAGE; $zip = $env:ZIP_FILE; Add-Type -AssemblyName System.IO.Compression.FileSystem; if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }; [System.IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $false)"

if errorlevel 1 (
  echo.
  echo Compression failed. Package was not created.
  rmdir /s /q "%STAGE%" >nul 2>nul
  exit /b 1
)

rmdir /s /q "%STAGE%" >nul 2>nul

echo.
echo Done. No git command was run, and .git was not included.
echo   %ZIP_FILE%
exit /b 0
