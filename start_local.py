#!/usr/bin/env python3
"""
Script pour démarrer l'API localement pour les tests
"""

import subprocess
import sys
import os

def check_tippecanoe():
    """Vérifie si Tippecanoe est installé"""
    try:
        result = subprocess.run(["tippecanoe", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def install_requirements():
    """Installe les dépendances Python"""
    print("📦 Installation des dépendances...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    print("🚀 Démarrage de l'API KML vers MBTiles")
    
    # Vérifier Tippecanoe
    if not check_tippecanoe():
        print("⚠️ Tippecanoe non trouvé!")
        print("Installation requise:")
        print("- macOS: brew install tippecanoe")
        print("- Ubuntu: sudo apt install tippecanoe")
        print("- Windows: Utiliser WSL ou Docker")
        print("\nL'API démarrera mais les conversions échoueront.")
    else:
        print("✅ Tippecanoe détecté")
    
    # Installer les dépendances
    install_requirements()
    
    # Démarrer l'API
    print("\n🌐 Démarrage du serveur sur http://localhost:8000")
    print("📖 Documentation: http://localhost:8000/docs")
    print("❤️ Health check: http://localhost:8000/health")
    print("\n🛑 Ctrl+C pour arrêter")
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur")

if __name__ == "__main__":
    main()