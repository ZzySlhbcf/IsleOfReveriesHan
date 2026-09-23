@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Isle of Reveries 简体中文补丁 - 安装

set "GAME=D:\Games\Steam\steamapps\common\Isle of Reveries"
set "PATCHVER=润色版 对白11x11/菜单与说明9x10 (2026-09-23)"
set "BASEMD5=e7ce2ff29ce2dfcbcbf7bf232ef2e97c"
set "PATCHMD5=57c99a77e9c7028aaab090d463029df6"

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
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TARGET -Algorithm MD5).Hash.ToLowerInvariant()"') do set "CURMD5=%%H"
if not defined CURMD5 (
  echo [错误] 无法读取当前游戏资源包的 MD5，安装已取消。
  pause
  exit /b 1
)

if /I "%CURMD5%"=="%PATCHMD5%" goto writepatch
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
