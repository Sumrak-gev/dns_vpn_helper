@echo off
echo ==========================================
echo  Building DNS & VPN Helper executable...
echo ==========================================

py -m pip install --upgrade pyinstaller customtkinter requests

py -m PyInstaller --noconsole --onefile --uac-admin ^
  --name "DNS_VPN_Helper" ^
  --add-data "config;config" ^
  --add-data "tools;tools" ^
  --collect-all customtkinter ^
  src/main.py

echo.
echo Build finished! Executable is located in the dist\ folder.
pause
