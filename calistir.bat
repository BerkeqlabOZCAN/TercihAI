@echo off
rem Tercih Robotu - terminal baslatici (web icin: "Tercih Robotu.bat")
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi. https://www.python.org adresinden kurun.
    pause
    exit /b 1
)

:menu
echo.
echo ============================================
echo   1 - Tercih Robotu (terminal)
echo   2 - Web arayuzu (tarayicida)
echo   3 - Tercih verisini yeniden indir
echo   0 - Cikis
echo ============================================
set /p secim="Seciminiz: "

if not exist veri.json (
    echo Veri bulunamadi, once indiriliyor...
    python veri_cek.py
)
if "%secim%"=="1" ( python tercih_robotu.py & goto menu )
if "%secim%"=="2" ( python app.py & goto menu )
if "%secim%"=="3" ( python veri_cek.py & goto menu )
if "%secim%"=="0" ( exit /b 0 )
goto menu
