@echo off
rem FASAS Digitale - avvio di prova su Windows (doppio clic su questo file).
rem Se la cartella e' stata scaricata con git, prima scarica gli aggiornamenti.
setlocal
cd /d "%~dp0"
echo === FASAS Digitale - avvio di prova ===

set HAS_GIT=0
where git >nul 2>nul && set HAS_GIT=1
if "%HAS_GIT%"=="1" if exist .git goto update
echo [!] Cartella non collegata a git: gli aggiornamenti non vengono scaricati in automatico.
goto afterupdate
:update
echo Scarico gli aggiornamenti...
git pull --ff-only
:afterupdate

if not exist .venv\Scripts\python.exe (
  echo Creo l'ambiente Python, solo la prima volta...
  py -m venv .venv 2>nul || python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo [!] Python non trovato. Installalo da https://www.python.org/downloads/ spuntando "Add Python to PATH".
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if not exist .env (>.env echo DJANGO_DEBUG=1)
python manage.py migrate --verbosity 0
python manage.py fasas_demo --skip-if-exists

echo.
echo Apri http://127.0.0.1:8000
echo Utenti: admin, coordinatore, operatore, medico, amministrativo - password: Demo-Fasas-2026!
echo Per fermare il sistema premi CTRL+C oppure chiudi questa finestra.
echo.
start "" /min cmd /c "ping -n 5 127.0.0.1 >nul & start http://127.0.0.1:8000"
python manage.py runserver
pause
