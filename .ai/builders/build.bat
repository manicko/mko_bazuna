@echo off
setlocal enabledelayedexpansion

echo.
echo ==================================================
echo BUILD START
echo ==================================================

:: ==================================================
:: PATHS
:: ==================================================

:: Folder where build.bat lives (.ai\builders), resolved to an absolute path.
set "SCRIPT_DIR=%~dp0"
:: Strip trailing backslash for clean joins below.
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
:: .ai\builders -> .ai -> project root: go up two levels for the repo root.
set "ROOT=%SCRIPT_DIR%\..\.."
set "DOCS_DIR=%ROOT%\docs"
:: Normalize to an absolute path so eza/tree headers are not shown with
:: unresolved "..\.." segments.
for %%I in ("%ROOT%\src") do set "SOURCE_DIR=%%~fI"

:: ==================================================
:: PROJECT TREE
:: ==================================================

echo.
echo [1/3] Generating project structure...
if not exist "%DOCS_DIR%" mkdir "%DOCS_DIR%"
if not exist "%ROOT%\.ai\structure" mkdir "%ROOT%\.ai\structure"

:: Prefer eza: its --git-ignore flag respects .gitignore, automatically
:: excluding __pycache__, .venv, node_modules, .env, etc. Fall back to the
:: legacy tree command if eza is unavailable (more visual noise).
where eza >nul 2>&1
if %errorlevel% equ 0 (
    eza --tree --git-ignore -L 3 "%SOURCE_DIR%" > "%DOCS_DIR%\STRUCT.md"
    eza --tree --git-ignore -L 3 "%SOURCE_DIR%" > "%ROOT%\.ai\structure\map.md"
) else (
    tree "%SOURCE_DIR%" /F /A > "%DOCS_DIR%\STRUCT.md" 2>nul
    tree "%SOURCE_DIR%" /F /A > "%ROOT%\.ai\structure\map.md" 2>nul
    echo [WARN] eza not found, using tree (includes __pycache__ noise)
)

echo Generated STRUCT.md

:: ==================================================
:: PYTHON SEMANTIC SCAN
:: ==================================================

echo.
echo [2/3] Running Python semantic scan...

uv run python "%SCRIPT_DIR%\back\py_map.py"

if %errorlevel% neq 0 (
    echo [ERROR] Python script failed!
    pause
    exit /b 1
)

echo Python scan complete

:: ==================================================
:: TYPESCRIPT SEMANTIC SCAN (optional)
:: ==================================================
:: The TS builder is gated by ENABLE_TS. For Mko Bazuna there is no frontend,
:: so it is disabled and the step is skipped. To enable on a TS project set
:: ENABLE_TS=true below (it requires no ts-node / ts-morph / js-yaml).

echo.
echo [3/3] Running frontend semantic scan...

if not exist "%SCRIPT_DIR%\front\ts_map.ts" (
    echo No TypeScript builder found, skipping.
    goto :done
)

set "ENABLE_TS=false"
node --experimental-strip-types "%SCRIPT_DIR%\front\ts_map.ts"

if %errorlevel% neq 0 (
    echo [ERROR] TypeScript scan failed!
    pause
    exit /b 1
)

echo Frontend scan complete

:done

echo.
echo ==================================================
echo BUILD COMPLETE
echo ==================================================

endlocal
pause
