@echo off
chcp 936 >nul
setlocal
title Isle of Reveries 简体中文补丁 - 卸载

set "GAME=D:\Games\Steam\steamapps\common\Isle of Reveries"
set "BASEMD5=e7ce2ff29ce2dfcbcbf7bf232ef2e97c"
set "PATCHMD5=d766a0ed010edbf6b1b615d1114056e1"


if not exist "%GAME%\www\assets.dat.cn-backup" (
  echo [错误] 没有找到备份文件 www\assets.dat.cn-backup, 无法自动还原.
  echo         可在 Steam 里右键游戏 - 属性 - 已安装文件 - 验证文件完整性 来还原.
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat"
set "CURMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "CURMD5=%%H"
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
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "BAKMD5=%%H"
if /I not "%BAKMD5%"=="%BASEMD5%" (
  echo [错误] 备份文件与本补丁对应的英文原版不匹配，拒绝还原。
  echo         请使用 Steam 的“验证文件完整性”。
  pause
  exit /b 1
)

copy /Y "%GAME%\www\assets.dat.cn-backup" "%GAME%\www\assets.dat" >nul
echo 已还原为英文原版. 备份文件保留在 www\assets.dat.cn-backup
pause
