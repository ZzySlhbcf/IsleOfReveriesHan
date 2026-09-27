@echo off
chcp 936 >nul
setlocal
title Isle of Reveries 简体中文补丁 - 卸载

set "GAME=D:\Games\Steam\steamapps\common\Isle of Reveries"
set "BASEMD5=06e9ffd80556cef82791cc1a84d0557d"
set "PATCHMD5=07977ea85dcd25761490167113d3925d"


if not exist "%GAME%\www\assets.dat.cn-backup" (
  echo [错误] 没有找到备份文件 www\assets.dat.cn-backup, 无法自动还原.
  echo         可在 Steam 里右键游戏 - 属性 - 已安装文件 - 验证文件完整性 来还原.
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat"
set "CURMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "([BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([IO.File]::ReadAllBytes($env:TARGET)))).Replace([string][char]45,[string]::Empty).ToLowerInvariant()"') do set "CURMD5=%%H"
if /I "%CURMD5%"=="%BASEMD5%" (
  echo 当前已经是与本补丁匹配的英文原版，无需卸载。
  pause
  exit /b 0
)
if /I not "%CURMD5%"=="%PATCHMD5%" (
  echo [错误] 当前资源包不是本补丁安装的版本，拒绝用旧备份覆盖。
  echo         若游戏刚更新，请使用 Steam 的“验证文件完整性”还原。
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat.cn-backup"
set "BAKMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "([BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([IO.File]::ReadAllBytes($env:TARGET)))).Replace([string][char]45,[string]::Empty).ToLowerInvariant()"') do set "BAKMD5=%%H"
if /I not "%BAKMD5%"=="%BASEMD5%" (
  echo [错误] 备份文件与本补丁对应的英文原版不匹配，拒绝还原。
  echo         请使用 Steam 的“验证文件完整性”。
  pause
  exit /b 1
)

copy /Y "%GAME%\www\assets.dat.cn-backup" "%GAME%\www\assets.dat" >nul
if errorlevel 1 (
  echo [错误] 还原失败，请先退出游戏，再重试。
  pause
  exit /b 1
)
set "TARGET=%GAME%\www\assets.dat"
set "RESTOREDMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "([BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([IO.File]::ReadAllBytes($env:TARGET)))).Replace([string][char]45,[string]::Empty).ToLowerInvariant()"') do set "RESTOREDMD5=%%H"
if /I not "%RESTOREDMD5%"=="%BASEMD5%" (
  echo [错误] 还原后的资源包校验失败，请勿继续使用，尝试 Steam 验证文件完整性。
  pause
  exit /b 1
)
echo 已还原整个英文原版资源包，汉化贴图、字体和文字均已撤销。
echo 英文备份保留在 www\assets.dat.cn-backup
pause
