#!/usr/bin/env python3
"""
Script de test pour l'API KML vers MBTiles
"""

import requests
import tempfile
import os

# KML de test simple
TEST_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Test KML</name>
    <Placemark>
      <name>Point Test</name>
      <Point>
        <coordinates>-1.116611,44.520414,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Ligne Test</name>
      <LineString>
        <coordinates>
          -1.116611,44.520414,0
          -1.130166,44.523935,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""

def test_api(base_url="http://localhost:8000"):
    """Test l'API de conversion"""
    
    print(f"🧪 Test de l'API: {base_url}")
    
    # Test 1: Health check
    print("\n1️⃣ Test de santé...")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ API en ligne: {health_data}")
            if not health_data.get('tippecanoe_available'):
                print("⚠️ Tippecanoe non disponible!")
        else:
            print(f"❌ Erreur health check: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Impossible de contacter l'API: {e}")
        return False
    
    # Test 2: Conversion KML
    print("\n2️⃣ Test de conversion KML...")
    try:
        # Créer un fichier KML temporaire
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kml', delete=False) as tmp_file:
            tmp_file.write(TEST_KML)
            tmp_file_path = tmp_file.name
        
        # Envoyer la requête
        with open(tmp_file_path, 'rb') as f:
            files = {'file': ('test.kml', f, 'application/vnd.google-earth.kml+xml')}
            data = {
                'min_zoom': 0,
                'max_zoom': 10,
                'name': 'test_conversion'
            }
            
            response = requests.post(
                f"{base_url}/convert-to-mbtiles",
                files=files,
                data=data,
                timeout=60
            )
        
        # Nettoyer
        os.unlink(tmp_file_path)
        
        if response.status_code == 200:
            print(f"✅ Conversion réussie! Taille MBTiles: {len(response.content)} bytes")
            
            # Sauvegarder le fichier de test
            with open("test_output.mbtiles", "wb") as f:
                f.write(response.content)
            print("💾 Fichier sauvegardé: test_output.mbtiles")
            
            return True
        else:
            print(f"❌ Erreur conversion: {response.status_code}")
            if response.headers.get('content-type') == 'application/json':
                print(f"Détails: {response.json()}")
            else:
                print(f"Réponse: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    # URL par défaut ou depuis les arguments
    api_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    success = test_api(api_url)
    
    if success:
        print("\n🎉 Tous les tests sont passés!")
    else:
        print("\n💥 Certains tests ont échoué!")
        sys.exit(1)