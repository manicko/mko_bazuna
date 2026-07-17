@echo off
setlocal enabledelayedexpansion

echo.
echo ==================================================
echo BUILD START
echo ==================================================

:: ==================================================
:: PATHS
:: ==================================================

:: Получаем путь к папке, где лежит build.bat
set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%..\.."
set "DOCS_DIR=%ROOT%\docs"
set "SOURCE_DIR=%ROOT%\src"

:: ==================================================
:: PROJECT TREE
:: ==================================================

echo.
echo [1/3] Generating project structure...
tree "%SOURCE_DIR%" /F /A > "%DOCS_DIR%\STRUCT.md" 2>nul
tree "%SOURCE_DIR%" /F /A > "%ROOT%\.ai\structure\map.md" 2>nul

echo Generated STRUCT.md

:: ==================================================
:: PYTHON SEMANTIC SCAN
:: ==================================================

echo.
echo [2/3] Running Python semantic scan...

python "%ROOT%\.ai\builders\back\py_map.py"

if %errorlevel% neq 0 (
    echo [ERROR] Python script failed!
    pause
    exit /b 1
)

echo Python scan complete

:: ==================================================
:: TYPESCRIPT SEMANTIC SCAN
:: ==================================================

echo.
echo [3/3] Running frontend semantic scan...

npx ts-node "%ROOT%\.ai\builders\front\ts_map.ts"

if %errorlevel% neq 0 (
    echo [ERROR] TypeScript scan failed!
    pause
    exit /b 1
)

echo Frontend scan complete

echo.
echo ==================================================
echo BUILD COMPLETE
echo ==================================================

endlocal
pause