@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -m streamlit run daily_planner_app.py) || (python -m streamlit run daily_planner_app.py)
