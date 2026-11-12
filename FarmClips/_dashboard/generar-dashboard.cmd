@echo off
chcp 65001 >nul
rem Genera el dashboard de la documentación (doble clic)
where py >nul 2>nul
if %errorlevel%==0 (py -3 "%~dp0generar.py" %*) else (python "%~dp0generar.py" %*)
echo.
pause
