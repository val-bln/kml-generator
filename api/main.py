from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
import subprocess
import json
import uuid
from pathlib import Path

app = FastAPI(title="KML to MBTiles Converter API")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "tippecanoe_available": check_tippecanoe()}

def check_tippecanoe():
    try:
        result = subprocess.run(["tippecanoe", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

@app.get("/")
async def root():
    return {"message": "API KML vers MBTiles", "status": "operational"}

@app.post("/convert-to-mbtiles")
async def convert_kml_to_mbtiles(
    file: UploadFile = File(...),
    min_zoom: int = 0,
    max_zoom: int = 14,
    name: str = "converted_tiles"
):
    if not file.filename.endswith('.kml'):
        raise HTTPException(status_code=400, detail="Le fichier doit être un KML")
    
    return {"message": "Conversion en cours de développement"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
