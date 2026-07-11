@echo off
if not "%~1" == "" (
    python -m bookcli.cli %*
    exit /b
)

:loop
cls
echo BookCLI Search Explorer
echo ----------------------
echo.
set /p query="Enter search query (or type 'exit' to close): "
if "%query%"=="exit" exit
if "%query%"=="q" exit
if "%query%"=="" goto loop

python -m bookcli.cli search "%query%"

echo.
echo ------------------------------------------
echo [1] Search another book
echo [2] Change default download directory
echo [3] Exit / Close window
echo ------------------------------------------
echo.
set /p choice="Choose an option (1, 2, or 3): "
if "%choice%"=="1" goto loop
if "%choice%"=="2" goto change_dl_dir
if "%choice%"=="3" exit
exit

:change_dl_dir
echo.
set /p new_path="Enter new default download directory path: "
if "%new_path%"=="" goto loop
python -m bookcli.cli config set download-dir "%new_path%"
echo.
pause
goto loop
