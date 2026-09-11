@echo off
title CSV Insight Agent Web Studio
echo =======================================================
echo  CSV Insight Agent - Modern Web Studio
echo  Starting local web application on http://127.0.0.1:5000
echo =======================================================
call .\venv\Scripts\activate.bat
python server.py
pause
