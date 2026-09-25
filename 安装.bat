@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Isle of Reveries 简体中文补丁 - 安装

set "GAME=D:\Games\Steam\steamapps\common\Isle of Reveries"
set "PATCHVER=润色版 对白11x11/菜单与说明9x10 (2026-09-25 小游戏对白修订)"
set "BASEMD5=c129bb8fa4beb49a4e8f23d0748be5fc"
set "PATCHMD5=6c46aaa2bf490928141009071b4c7e86"
set "PREVMD5=7379f8028660fd0512323822dd5160aa"
set "PREVMD5_OLDER=f9f817d38d2628237f566e6bac44ca02"

if not exist "%GAME%\Isle_of_Reveries.exe" (
  echo [错误] 没有找到游戏目录: %GAME%
  echo         请用记事本打开本文件, 把上面的 GAME= 改成你的游戏安装路径后重试.
  pause
  exit /b 1
)

if not exist "%GAME%\www\assets.dat" (
  echo [错误] 没有找到 %GAME%\www\assets.dat
  pause
  exit /b 1
)

set "TARGET=%GAME%\www\assets.dat"
set "CURMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "([BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([IO.File]::ReadAllBytes($env:TARGET)))).Replace([string][char]45,[string]::Empty).ToLowerInvariant()"') do set "CURMD5=%%H"
if not defined CURMD5 (
  echo [错误] 无法读取当前游戏资源包的 MD5，安装已取消。
  pause
  exit /b 1
)

if /I "%CURMD5%"=="%PATCHMD5%" goto writepatch
if defined PREVMD5 if /I "%CURMD5%"=="%PREVMD5%" goto upgrade
if defined PREVMD5_OLDER if /I "%CURMD5%"=="%PREVMD5_OLDER%" goto upgrade
if /I not "%CURMD5%"=="%BASEMD5%" (
  echo [错误] 当前游戏资源版本与本补丁不匹配，安装已取消。
  echo         这通常表示游戏刚刚更新；请运行 官方更新后重建.bat，
  echo         不要用旧 assets.dat 覆盖新版游戏，否则可能出现无声或资源异常。
  pause
  exit /b 1
)

echo 备份当前匹配的英文原版 www\assets.dat -^> www\assets.dat.cn-backup
copy /Y "%GAME%\www\assets.dat" "%GAME%\www\assets.dat.cn-backup" >nul
if errorlevel 1 (
  echo [错误] 备份失败，安装已取消。
  pause
  exit /b 1
)

goto writepatch

:upgrade
if not exist "%GAME%\www\assets.dat.cn-backup" (
  echo [错误] 找不到英文原版备份，不能从旧版汉化直接升级。
  pause
  exit /b 1
)
set "TARGET=%GAME%\www\assets.dat.cn-backup"
set "BAKMD5="
for /f "delims=" %%H in ('powershell -NoProfile -Command "([BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([IO.File]::ReadAllBytes($env:TARGET)))).Replace([string][char]45,[string]::Empty).ToLowerInvariant()"') do set "BAKMD5=%%H"
if /I not "%BAKMD5%"=="%BASEMD5%" (
  echo [错误] 英文备份与新版游戏资源不匹配，拒绝覆盖旧版汉化。
  pause
  exit /b 1
)
echo 已确认旧版汉化与英文备份属于同一游戏版本，保留备份并升级。

:writepatch
echo 写入汉化资源包 ^(版本: %PATCHVER%^) ...
copy /Y "%~dp0www\assets.dat" "%GAME%\www\assets.dat" >nul
if errorlevel 1 (
  echo [错误] 写入失败, 请确认游戏没有在运行.
  pause
  exit /b 1
)

for %%I in ("%~dp0www\assets.dat") do set "SRCSIZE=%%~zI"
for %%I in ("%GAME%\www\assets.dat") do set "DSTSIZE=%%~zI"
if not "%SRCSIZE%"=="%DSTSIZE%" (
  echo [错误] 校验失败: 源 %SRCSIZE% 字节, 目标 %DSTSIZE% 字节.
  pause
  exit /b 1
)

echo.
echo 安装完成! 版本 %PATCHVER% ^(%DSTSIZE% 字节^)
echo 启动游戏即为简体中文; 卸载请运行 卸载.bat.
echo.
pause
