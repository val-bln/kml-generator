from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
import subprocess
import json
import uuid
from pathlib import Path

app = FastAPI(title="KML to MBTiles Converter API")

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
        convert_kml_to_geojson(kml_path, ge
