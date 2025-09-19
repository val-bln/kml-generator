@echo off
echo Installation des dépendances...
pip install -r requirements.txt

echo Lancement de l'application...
streamlit run streamlit_app.py

pause