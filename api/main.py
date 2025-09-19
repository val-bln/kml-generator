from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
import subprocess
import json
import uuid
from pathlib import Path

app = FastAPI(title="KML to MBTiles Converter API")

@app.get("/")
async def root():
    """Endpoint racine"""
    return {"message": "KML to MBTiles Converter API", "status": "running"}

@app.post("/convert-to-mbtiles")
async def convert_kml_to_mbtiles(
    file: UploadFile = File(...),
    min_zoom: int = 0,
    max_zoom: int = 14,
    name: str = "converted_tiles"
):
    """Convertit un fichier KML en MBTiles via Tippecanoe"""
    
    if not file.filename.endswith('.kml'):
        raise HTTPException(status_code=400, detail="Le fichier doit être un KML")
    
    # Créer un dossier temporaire unique
    temp_dir = Path(tempfile.mkdtemp())
    temp_id = str(uuid.uuid4())
    
    try:
        # Sauvegarder le fichier KML
        kml_path = temp_dir / f"{temp_id}.kml"
        with open(kml_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Convertir KML en GeoJSON (requis par Tippecanoe)
        geojson_path = temp_dir / f"{temp_id}.geojson"
        convert_kml_to_geojson(kml_path, geojson_path)
        
        # Générer MBTiles avec Tippecanoe
        mbtiles_path = temp_dir / f"{name}.mbtiles"
        
        tippecanoe_cmd = [
            "tippecanoe",
            "-o", str(mbtiles_path),
            "-z", str(max_zoom),
            "-Z", str(min_zoom),
            "--force",
            "--drop-densest-as-needed",
            str(geojson_path)
        ]
        
        result = subprocess.run(tippecanoe_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500, 
                detail=f"Erreur Tippecanoe: {result.stderr}"
            )
        
        # Retourner le fichier MBTiles
        return FileResponse(
            path=mbtiles_path,
            filename=f"{name}.mbtiles",
            media_type="application/octet-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Nettoyage (optionnel, les fichiers temp seront supprimés automatiquement)
        pass

def convert_kml_to_geojson(kml_path: Path, geojson_path: Path):
    """Convertit KML en GeoJSON simple"""
    try:
        # Utiliser ogr2ogr si disponible
        cmd = [
            "ogr2ogr", 
            "-f", "GeoJSON", 
            str(geojson_path), 
            str(kml_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # Fallback: conversion manuelle basique
            convert_kml_manual(kml_path, geojson_path)
            
    except FileNotFoundError:
        # ogr2ogr non disponible, conversion manuelle
        convert_kml_manual(kml_path, geojson_path)

def convert_kml_manual(kml_path: Path, geojson_path: Path):
    """Conversion KML vers GeoJSON manuelle basique"""
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Namespace KML
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    features = []
    
    # Extraire les placemarks
    for placemark in root.findall('.//kml:Placemark', ns):
        name = placemark.find('kml:name', ns)
        name_text = name.text if name is not None else "Unnamed"
        
        # Points
        point = placemark.find('.//kml:Point/kml:coordinates', ns)
        if point is not None:
            coords = point.text.strip().split(',')
            if len(coords) >= 2:
                feature = {
                    "type": "Feature",
                    "properties": {"name": name_text},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(coords[0]), float(coords[1])]
                    }
                }
                features.append(feature)
        
        # LineStrings
        linestring = placemark.find('.//kml:LineString/kml:coordinates', ns)
        if linestring is not None:
            coords_text = linestring.text.strip()
            coords = []
            for coord_pair in coords_text.split():
                parts = coord_pair.split(',')
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            
            if coords:
                feature = {
                    "type": "Feature",
                    "properties": {"name": name_text},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    }
                }
                features.append(feature)
        
        # Polygons
        polygon = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
        if polygon is not None:
            coords_text = polygon.text.strip()
            coords = []
            for coord_pair in coords_text.split():
                parts = coord_pair.split(',')
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            
            if coords:
                feature = {
                    "type": "Feature",
                    "properties": {"name": name_text},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                }
                features.append(feature)
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    with open(geojson_path, 'w') as f:
        json.dump(geojson, f)

@app.get("/health")
async def health_check():
    """Vérification de l'état de l'API"""
    return {"status": "healthy", "tippecanoe_available": check_tippecanoe()}

def check_tippecanoe():
    """Vérifie si Tippecanoe est disponible"""
    try:
        result = subprocess.run(["tippecanoe", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)