from fastapi import FastAPI

app = FastAPI(title="KML to MBTiles API")

@app.get("/health")
def health():
    return {"status": "healthy", "tippecanoe_available": False}

@app.get("/")
def root():
    return {"message": "API MBTiles - En cours de développement"}
