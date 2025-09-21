from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
import subprocess
import json
import uuid
import re
from pathlib import Path

app = FastAPI(title="KML to MBTiles Converter API")

@app.get("/")
async def root():
    """Endpoint racine"""
    return {"message": "KML to MBTiles Converter API", "status": "running"}

@app.post("/convert-geojson-to-mbtiles")
async def convert_geojson_to_mbtiles(
    file: UploadFile = File(...),
    min_zoom: int = 0,
    max_zoom: int = 14,
    name: str = "converted_tiles",
    preserve_properties: bool = True,
    simplification: float = 0.0
):
    """Convertit un fichier GeoJSON en MBTiles via Tippecanoe"""
    
    if not file.filename.endswith('.geojson'):
        raise HTTPException(status_code=400, detail="Le fichier doit être un GeoJSON")
    
    # Créer un dossier temporaire unique
    temp_dir = Path(tempfile.mkdtemp())
    temp_id = str(uuid.uuid4())
    
    try:
        # Sauvegarder le fichier GeoJSON
        geojson_path = temp_dir / f"{temp_id}.geojson"
        with open(geojson_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Générer MBTiles avec Tippecanoe - paramètres compatibles SDVFR
        mbtiles_path = temp_dir / f"{name}.mbtiles"
        
        # Paramètres d'origine qui ne faisaient pas planter SDVFR
        tippecanoe_cmd = [
            "tippecanoe",
            "-o", str(mbtiles_path),
            "-z", str(max_zoom),
            "-Z", str(min_zoom),
            "--force"
        ]
        
        # Paramètres de base pour assurer la génération
        if simplification == 0.0:
            tippecanoe_cmd.extend([
                "--no-simplification",
                "--no-feature-limit",
                "--no-tile-size-limit"
            ])
        else:
            tippecanoe_cmd.extend(["-S", str(simplification)])
            
        # Préserver les propriétés de base
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
            "--force"
        ]
        
        # Paramètres de base pour assurer la génération
        if simplification == 0.0:
            tippecanoe_cmd.extend([
                "--no-simplification",
                "--no-feature-limit",
                "--no-tile-size-limit"
            ])
        else:
            tippecanoe_cmd.extend(["-S", str(simplification)])
            
        # Préserver les propriétés de base
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
    """Convertit KML en GeoJSON en préservant la structure des polygones"""
    try:
        # Utiliser ogr2ogr avec options pour préserver les polygones
        cmd = [
            "ogr2ogr", 
            "-f", "GeoJSON",
            "-preserve_fid",
            "-lco", "RFC7946=NO",  # Préserver la structure originale
            str(geojson_path), 
            str(kml_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # Fallback: conversion manuelle optimisée
            convert_kml_manual(kml_path, geojson_path)
            
    except FileNotFoundError:
        # ogr2ogr non disponible, conversion manuelle
        convert_kml_manual(kml_path, geojson_path)

def convert_kml_manual(kml_path: Path, geojson_path: Path):
    """Conversion KML vers GeoJSON avec parsing robuste des coordonnées"""
    import xml.etree.ElementTree as ET
    import re
    
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Namespace KML
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    features = []
    
    # Extraire les styles définis
    styles = {}
    for style in root.findall('.//kml:Style', ns):
        style_id = style.get('id')
        if style_id:
            styles[style_id] = extract_style_properties(style, ns)
    
    # Extraire les placemarks
    for placemark in root.findall('.//kml:Placemark', ns):
        properties = {}
        
        # Extraire toutes les propriétés
        name = placemark.find('kml:name', ns)
        if name is not None and name.text:
            properties['name'] = name.text.strip()
            
        description = placemark.find('kml:description', ns)
        if description is not None and description.text:
            properties['description'] = description.text.strip()
            
        # Extraire les données étendues
        for extended_data in placemark.findall('.//kml:ExtendedData/kml:Data', ns):
            data_name = extended_data.get('name')
            value_elem = extended_data.find('kml:value', ns)
            if data_name and value_elem is not None and value_elem.text:
                properties[data_name] = value_elem.text.strip()
        
        # Extraire et appliquer les styles
        style_props = extract_placemark_style(placemark, styles, ns)
        properties.update(style_props)
            
        # Points
        point = placemark.find('.//kml:Point/kml:coordinates', ns)
        if point is not None and point.text:
            coords = parse_coordinates(point.text)
            if coords and len(coords) == 1:
                properties.setdefault('marker-color', '#ff0000')
                properties.setdefault('marker-size', 'medium')
                properties.setdefault('marker-symbol', 'circle')
                    
                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Point",
                        "coordinates": coords[0]
                    }
                }
                features.append(feature)
        
        # LineStrings
        linestring = placemark.find('.//kml:LineString/kml:coordinates', ns)
        if linestring is not None and linestring.text:
            coords = parse_coordinates(linestring.text)
            if coords and len(coords) >= 2:
                properties.setdefault('stroke', '#ff0000')
                properties.setdefault('stroke-width', 2)
                properties.setdefault('stroke-opacity', 1.0)
                    
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
            outer_ring = polygon.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if outer_ring is not None and outer_ring.text:
                outer_coords = parse_coordinates(outer_ring.text)
                
                if outer_coords and len(outer_coords) >= 3:
                    # Assurer que le polygone est fermé
                    if outer_coords[0] != outer_coords[-1]:
                        outer_coords.append(outer_coords[0])
                    
                    # Inner boundaries (holes)
                    inner_coords = []
                    for inner_ring in polygon.findall('.//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates', ns):
                        if inner_ring.text:
                            hole_coords = parse_coordinates(inner_ring.text)
                            if hole_coords and len(hole_coords) >= 3:
                                if hole_coords[0] != hole_coords[-1]:
                                    hole_coords.append(hole_coords[0])
                                inner_coords.append(hole_coords)
                    
                    polygon_coords = [outer_coords] + inner_coords
                    
                    properties.setdefault('stroke', '#ff0000')
                    properties.setdefault('stroke-width', 2)
                    properties.setdefault('stroke-opacity', 1.0)
                    properties.setdefault('fill', '#ff0000')
                    properties.setdefault('fill-opacity', 0.3)
                        
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

def parse_coordinates(coord_text):
    """Parse robuste des coordonnées KML"""
    if not coord_text:
        return []
    
    coords = []
    # Nettoyer le texte et séparer par espaces ou retours à la ligne
    coord_text = re.sub(r'\s+', ' ', coord_text.strip())
    
    # Séparer les triplets de coordonnées
    coord_pairs = []
    for part in coord_text.split():
        if ',' in part:
            coord_pairs.append(part)
        elif coord_pairs:  # Continuer le dernier triplet si pas de virgule
            coord_pairs[-1] += ' ' + part
    
    for coord_pair in coord_pairs:
        try:
            parts = coord_pair.strip().split(',')
            if len(parts) >= 2:
                lon = float(parts[0].strip())
                lat = float(parts[1].strip())
                coord = [lon, lat]
                if len(parts) >= 3 and parts[2].strip():
                    coord.append(float(parts[2].strip()))  # altitude
                coords.append(coord)
        except (ValueError, IndexError):
            continue
    
    return coords

def extract_style_properties(style_elem, ns):
    """Extrait les propriétés de style d'un élément Style KML"""
    style_props = {}
    
    # LineStyle
    line_style = style_elem.find('kml:LineStyle', ns)
    if line_style is not None:
        color_elem = line_style.find('kml:color', ns)
        width_elem = line_style.find('kml:width', ns)
        
        if color_elem is not None:
            kml_color = color_elem.text.strip().lower()
            style_props['stroke'] = kml_color_to_hex(kml_color)
            style_props['stroke-opacity'] = kml_color_to_opacity(kml_color)
            
        if width_elem is not None:
            style_props['stroke-width'] = float(width_elem.text)
    
    # PolyStyle
    poly_style = style_elem.find('kml:PolyStyle', ns)
    if poly_style is not None:
        color_elem = poly_style.find('kml:color', ns)
        fill_elem = poly_style.find('kml:fill', ns)
        
        if color_elem is not None:
            kml_color = color_elem.text.strip().lower()
            style_props['fill'] = kml_color_to_hex(kml_color)
            style_props['fill-opacity'] = kml_color_to_opacity(kml_color)
            
        if fill_elem is not None:
            style_props['fill-opacity'] = 1.0 if fill_elem.text == '1' else 0.0
    
    # IconStyle pour les points
    icon_style = style_elem.find('kml:IconStyle', ns)
    if icon_style is not None:
        color_elem = icon_style.find('kml:color', ns)
        scale_elem = icon_style.find('kml:scale', ns)
        
        if color_elem is not None:
            kml_color = color_elem.text.strip().lower()
            style_props['marker-color'] = kml_color_to_hex(kml_color)
            
        if scale_elem is not None:
            style_props['marker-size'] = float(scale_elem.text) * 10  # Conversion échelle
    
    return style_props

def extract_placemark_style(placemark, styles, ns):
    """Extrait le style d'un placemark"""
    style_props = {}
    
    # Style inline
    inline_style = placemark.find('kml:Style', ns)
    if inline_style is not None:
        style_props.update(extract_style_properties(inline_style, ns))
    
    # Style référencé
    style_url = placemark.find('kml:styleUrl', ns)
    if style_url is not None:
        style_id = style_url.text.replace('#', '')
        if style_id in styles:
            style_props.update(styles[style_id])
    
    return style_props

def kml_color_to_hex(kml_color):
    """Convertit une couleur KML (AABBGGRR) en hex (#RRGGBB)"""
    if len(kml_color) == 8:
        # KML: AABBGGRR -> Hex: #RRGGBB
        r = kml_color[6:8]
        g = kml_color[4:6]
        b = kml_color[2:4]
        return f"#{r}{g}{b}"
    return "#ff0000"  # Rouge par défaut

def kml_color_to_opacity(kml_color):
    """Extrait l'opacité d'une couleur KML"""
    if len(kml_color) == 8:
        alpha = int(kml_color[0:2], 16)
        return alpha / 255.0
    return 1.0

@app.post("/convert-geojson-minimal")
async def convert_geojson_minimal(
    file: UploadFile = File(...),
    name: str = "minimal_tiles"
):
    """Conversion GeoJSON vers MBTiles avec paramètres ultra-minimaux"""
    
    if not file.filename.endswith('.geojson'):
        raise HTTPException(status_code=400, detail="Le fichier doit être un GeoJSON")
    
    temp_dir = Path(tempfile.mkdtemp())
    temp_id = str(uuid.uuid4())
    
    try:
        # Sauvegarder le fichier GeoJSON
        geojson_path = temp_dir / f"{temp_id}.geojson"
        with open(geojson_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # MBTiles avec paramètres ULTRA-minimaux
        mbtiles_path = temp_dir / f"{name}.mbtiles"
        
        # Commande Tippecanoe la plus simple possible
        tippecanoe_cmd = [
            "tippecanoe",
            "-o", str(mbtiles_path),
            str(geojson_path)
        ]
        
        result = subprocess.run(tippecanoe_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500, 
                detail=f"Erreur Tippecanoe: {result.stderr}"
            )
        
        return FileResponse(
            path=mbtiles_path,
            filename=f"{name}.mbtiles",
            media_type="application/octet-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/debug-kml")
async def debug_kml_conversion(file: UploadFile = File(...)):
    """Debug de la conversion KML vers GeoJSON"""
    if not file.filename.endswith('.kml'):
        raise HTTPException(status_code=400, detail="Le fichier doit être un KML")
    
    temp_dir = Path(tempfile.mkdtemp())
    temp_id = str(uuid.uuid4())
    
    try:
        # Sauvegarder le fichier KML
        kml_path = temp_dir / f"{temp_id}.kml"
        with open(kml_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Convertir en GeoJSON
        geojson_path = temp_dir / f"{temp_id}.geojson"
        convert_kml_to_geojson(kml_path, geojson_path)
        
        # Lire le GeoJSON généré
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
        
        return {
            "kml_size": len(content),
            "features_count": len(geojson_data.get('features', [])),
            "geojson": geojson_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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