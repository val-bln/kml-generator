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
    name: str = "converted_tiles",
    preserve_properties: bool = True,
    simplification: float = 0.0
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
            "--no-feature-limit",
            "--no-tile-size-limit"
        ]
        
        # Préserver la géométrie si demandé
        if simplification == 0.0:
            tippecanoe_cmd.extend(["--no-simplification", "--no-tiny-polygon-reduction"])
        else:
            tippecanoe_cmd.extend(["-S", str(simplification)])
            
        # Préserver toutes les propriétés
        if preserve_properties:
            tippecanoe_cmd.append("--preserve-input-order")
            
        tippecanoe_cmd.append(str(geojson_path))
        
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
    """Conversion KML vers GeoJSON avec préservation maximale des données"""
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Namespace KML
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    features = []
    
    # Extraire les placemarks
    for placemark in root.findall('.//kml:Placemark', ns):
        properties = {}
        
        # Extraire toutes les propriétés
        name = placemark.find('kml:name', ns)
        if name is not None:
            properties['name'] = name.text
            
        description = placemark.find('kml:description', ns)
        if description is not None:
            properties['description'] = description.text
            
        # Extraire les données étendues
        for extended_data in placemark.findall('.//kml:ExtendedData/kml:Data', ns):
            data_name = extended_data.get('name')
            value_elem = extended_data.find('kml:value', ns)
            if data_name and value_elem is not None:
                properties[data_name] = value_elem.text
        
        # Extraire les styles
        style_url = placemark.find('kml:styleUrl', ns)
        if style_url is not None:
            properties['styleUrl'] = style_url.text
            
        # Points
        point = placemark.find('.//kml:Point/kml:coordinates', ns)
        if point is not None:
            coords_text = point.text.strip()
            coords = coords_text.split(',')
            if len(coords) >= 2:
                coordinates = [float(coords[0]), float(coords[1])]
                if len(coords) >= 3:
                    coordinates.append(float(coords[2]))  # altitude
                    
                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates
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
                    coord = [float(parts[0]), float(parts[1])]
                    if len(parts) >= 3:
                        coord.append(float(parts[2]))  # altitude
                    coords.append(coord)
            
            if coords:
                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    }
                }
                features.append(feature)
        
        # Polygons
        polygon = placemark.find('.//kml:Polygon', ns)
        if polygon is not None:
            # Outer boundary
            outer_coords = []
            outer_ring = polygon.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if outer_ring is not None:
                coords_text = outer_ring.text.strip()
                for coord_pair in coords_text.split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        coord = [float(parts[0]), float(parts[1])]
                        if len(parts) >= 3:
                            coord.append(float(parts[2]))  # altitude
                        outer_coords.append(coord)
            
            # Inner boundaries (holes)
            inner_coords = []
            for inner_ring in polygon.findall('.//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates', ns):
                hole_coords = []
                coords_text = inner_ring.text.strip()
                for coord_pair in coords_text.split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        coord = [float(parts[0]), float(parts[1])]
                        if len(parts) >= 3:
                            coord.append(float(parts[2]))  # altitude
                        hole_coords.append(coord)
                if hole_coords:
                    inner_coords.append(hole_coords)
            
            if outer_coords:
                polygon_coords = [outer_coords] + inner_coords
                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": polygon_coords
                    }
                }
                features.append(feature)
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    with open(geojson_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

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