@echo off
rem Opens the Subnautica 2 modkit editor with its caches and temp files inside SN2_MODKIT_DIR (from <repo>\local.config),
rem so nothing large lands on the system drive. Always start the editor with this file, not by double-clicking the .uproject.
setlocal
set "SN2_REPO=%~dp0..\.."
for %%I in ("%SN2_REPO%") do set "SN2_REPO=%%~fI"
if not exist "%SN2_REPO%\local.config" (
  echo local.config not found in %SN2_REPO% - copy local.config.example to local.config and edit it.
  pause
  exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%SN2_REPO%\local.config") do set "%%a=%%~b"
if not defined SN2_MODKIT_DIR (
  echo SN2_MODKIT_DIR is not set in local.config
  pause
  exit /b 1
)
set "SN2_MODKIT_DIR=%SN2_MODKIT_DIR:/=\%"
if not defined SN2_ENGINE_DIR set "SN2_ENGINE_DIR=%SN2_MODKIT_DIR%\UE_5.6_SN2"
set "TEMP=%SN2_MODKIT_DIR%\Temp"
set "TMP=%SN2_MODKIT_DIR%\Temp"
set "UE-LocalDataCachePath=%SN2_MODKIT_DIR%\DDC"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%SN2_MODKIT_DIR%\DDC" mkdir "%SN2_MODKIT_DIR%\DDC"
start "" "%SN2_ENGINE_DIR%\Engine\Binaries\Win64\UnrealEditor.exe" "%SN2_MODKIT_DIR%\Subnautica2-Project\Subnautica2.uproject" %*
