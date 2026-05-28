@echo off
echo ============================================
echo   SEO Command Center - Setup & Launch
echo ============================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting dashboard...
echo.
echo Dashboard will open at: http://localhost:8501
echo.
streamlit run app.py --server.port 8501
pause
