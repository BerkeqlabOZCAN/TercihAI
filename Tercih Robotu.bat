@echo off
rem Tercih Robotu - cift tikla, tarayicida acilir
chcp 65001 >nul
cd /d "%~dp0"
title Tercih Robotu

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi. https://www.python.org adresinden kurun.
    pause
    exit /b 1
)

if not exist veri.json (
    echo Tercih verisi ilk kez indiriliyor, lutfen bekleyin...
    python veri_cek.py
)

echo.
echo   Tercih Robotu baslatiliyor... Tarayici otomatik acilacak.
echo   Kapatmak icin bu pencereyi kapatin.
echo.
python app.py
pause
