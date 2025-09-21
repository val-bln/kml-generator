import streamlit as st
import simplekml
import math
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import openpyxl
from io import BytesIO
import base64
import xml.etree.ElementTree as ET
import re
import tempfile
import os
import json
import sqlite3
import struct
import zlib
import requests

# Configuration API directe
API_BASE_URL = "https://kml-api-docker.onrender.com"
API_TIMEOUT = 300
MAX_KML_SIZE_MB = 50

def get_api_url():
    return API_BASE_URL

def is_api_configured():
    return not API_BASE_URL.startswith("https://your-api-url")

try:
    import rasterio
    from rasterio.warp import transform_bounds
    from PIL import Image
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False

# Détection iPad via User-Agent
def is_ipad():
    try:
        user_agent = st.context.headers.get("User-Agent", "")
        return "iPad" in user_agent
    except:
        return False

# Configuration spécifique iPad
if is_ipad():
    st.set_page_config(
        page_title="KML Generator - iPad",
        layout="centered",  # Layout centré pour iPad
        initial_sidebar_state="collapsed",
        menu_items=None
    )
else:
    st.set_page_config(
        page_title="Générateur KML pour SDVFR",
        layout="wide",
        initial_sidebar_state="collapsed",
        menu_items=None
    )

# Initialisation des données de session
if 'points_data' not in st.session_state:
    st.session_state.points_data = []
if 'lines_data' not in st.session_state:
    st.session_state.lines_data = []
if 'circles_data' not in st.session_state:
    st.session_state.circles_data = []
if 'rectangles_data' not in st.session_state:
    st.session_state.rectangles_data = []
if 'current_line_points' not in st.session_state:
    st.session_state.current_line_points = []
if 'current_polygon_points' not in st.session_state:
    st.session_state.current_polygon_points = []
if 'custom_tiles' not in st.session_state:
    st.session_state.custom_tiles = []
if 'clicked_position' not in st.session_state:
    st.session_state.clicked_position = None
if 'reference_data' not in st.session_state:
    st.session_state.reference_data = {'points': [], 'lines': [], 'polygons': []}
if 'show_reference' not in st.session_state:
    st.session_state.show_reference = True
if 'sdvfr_structure' not in st.session_state:
    st.session_state.sdvfr_structure = None
if 'reference_kml_data' not in st.session_state:
    st.session_state.reference_kml_data = None

# Constantes WGS84
WGS84_A = 6378137.0
WGS84_F = 1/298.257223563
WGS84_B = WGS84_A * (1 - WGS84_F)

# Fonctions géodésiques (version simplifiée pour iPad)
def calculate_distance(lat1, lon1, lat2, lon2):
    """Distance simplifiée pour iPad"""
    R = 6371000  # Rayon terrestre en mètres
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Gisement simplifié pour iPad"""
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    
    y = math.sin(dlon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360

def create_point_from_bearing_distance(center_point, distance_km, bearing_deg):
    """Création de point simplifié pour iPad"""
    R = 6371.0  # Rayon terrestre en km
    lat1_rad = math.radians(center_point["lat"])
    lon1_rad = math.radians(center_point["lon"])
    bearing_rad = math.radians(bearing_deg)
    
    lat2_rad = math.asin(math.sin(lat1_rad) * math.cos(distance_km/R) + 
                        math.cos(lat1_rad) * math.sin(distance_km/R) * math.cos(bearing_rad))
    
    lon2_rad = lon1_rad + math.atan2(math.sin(bearing_rad) * math.sin(distance_km/R) * math.cos(lat1_rad),
                                    math.cos(distance_km/R) - math.sin(lat1_rad) * math.sin(lat2_rad))
    
    return math.degrees(lat2_rad), math.degrees(lon2_rad)

def calculate_circle_points(center_lat, center_lon, radius_km, num_segments=16):
    """Cercle simplifié pour iPad"""
    points = []
    center_point = {"lat": center_lat, "lon": center_lon}
    
    for i in range(num_segments + 1):
        angle_deg = (360 / num_segments) * i
        new_lat, new_lon = create_point_from_bearing_distance(center_point, radius_km, angle_deg)
        points.append((new_lon, new_lat))
    
    return points

def generate_kml():
    """Génération KML simplifiée"""
    kml = simplekml.Kml()
    
    # Points
    for point in st.session_state.points_data:
        pnt = kml.newpoint(name=point['name'])
        pnt.coords = [(point['lon'], point['lat'])]
        pnt.description = f"Lat: {point['lat']:.6f}, Lon: {point['lon']:.6f}"
    
    # Lignes
    for line in st.session_state.lines_data:
        linestring = kml.newlinestring(name=line['name'])
        linestring.coords = [(p['lon'], p['lat']) for p in line['points']]
    
    # Cercles
    for circle in st.session_state.circles_data:
        points = calculate_circle_points(circle['lat'], circle['lon'], circle['radius'])
        polygon = kml.newpolygon(name=circle['name'])
        polygon.outerboundaryis = points
    
    return kml.kml()

def create_map():
    """Carte simplifiée pour iPad"""
    if st.session_state.points_data:
        center_lat = sum(p['lat'] for p in st.session_state.points_data) / len(st.session_state.points_data)
        center_lon = sum(p['lon'] for p in st.session_state.points_data) / len(st.session_state.points_data)
    else:
        center_lat, center_lon = 46.603354, 1.888334  # Centre France
    
    # Carte ultra-légère pour iPad
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles='OpenStreetMap',
        prefer_canvas=True  # Optimisation performance
    )
    
    # Limiter à 10 points maximum pour iPad
    display_points = st.session_state.points_data[:10] if is_ipad() else st.session_state.points_data
    
    # Ajouter les points
    for point in display_points:
        folium.Marker(
            [point['lat'], point['lon']],
            popup=point['name'],
            tooltip=point['name']
        ).add_to(m)
    
    # Ajouter les lignes (simplifiées)
    for line in st.session_state.lines_data[:5]:  # Max 5 lignes pour iPad
        coords = [[p['lat'], p['lon']] for p in line['points']]
        folium.PolyLine(coords, popup=line['name']).add_to(m)
    
    # Ajouter les cercles (simplifiés)
    for circle in st.session_state.circles_data[:3]:  # Max 3 cercles pour iPad
        folium.Circle(
            [circle['lat'], circle['lon']],
            radius=circle['radius'] * 1000,
            popup=circle['name']
        ).add_to(m)
    
    return m

# Interface utilisateur adaptée iPad
def main():
    if is_ipad():
        st.title("🗺️ KML Generator - iPad")
        st.info("Interface optimisée pour iPad")
        
        # Interface ultra-simplifiée pour iPad
        tab1, tab2, tab3 = st.tabs(["📍 Points", "🗺️ Carte", "📁 Export"])
        
        with tab1:
            st.subheader("Ajouter un point")
            col1, col2 = st.columns(2)
            with col1:
                lat = st.number_input("Latitude", value=46.603354, format="%.6f")
                name = st.text_input("Nom du point", value="Point")
            with col2:
                lon = st.number_input("Longitude", value=1.888334, format="%.6f")
                if st.button("Ajouter"):
                    st.session_state.points_data.append({
                        'name': name,
                        'lat': lat,
                        'lon': lon
                    })
                    st.success(f"Point {name} ajouté")
            
            # Liste des points (limitée)
            if st.session_state.points_data:
                st.subheader(f"Points ({len(st.session_state.points_data)})")
                for i, point in enumerate(st.session_state.points_data[:10]):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.text(f"{point['name']}: {point['lat']:.4f}, {point['lon']:.4f}")
                    with col2:
                        if st.button("🗑️", key=f"del_{i}"):
                            st.session_state.points_data.pop(i)
                            st.rerun()
        
        with tab2:
            st.subheader("Carte")
            if st.session_state.points_data or st.session_state.lines_data or st.session_state.circles_data:
                map_obj = create_map()
                st_folium(map_obj, width=700, height=300)  # Hauteur réduite pour iPad
            else:
                st.info("Ajoutez des points pour voir la carte")
        
        with tab3:
            st.subheader("Export KML")
            if st.session_state.points_data or st.session_state.lines_data or st.session_state.circles_data:
                if st.button("Générer KML"):
                    kml_content = generate_kml()
                    st.download_button(
                        label="Télécharger KML",
                        data=kml_content,
                        file_name="export_ipad.kml",
                        mime="application/vnd.google-earth.kml+xml"
                    )
            else:
                st.info("Aucune donnée à exporter")
            
            # Import KML simplifié
            st.subheader("Import KML")
            uploaded_file = st.file_uploader("Choisir un fichier KML", type=['kml'])
            if uploaded_file:
                try:
                    content = uploaded_file.read().decode('utf-8')
                    root = ET.fromstring(content)
                    
                    # Parser simple pour points
                    for placemark in root.iter():
                        if placemark.tag.endswith('Placemark'):
                            name_elem = placemark.find('.//{http://www.opengis.net/kml/2.2}name')
                            point_elem = placemark.find('.//{http://www.opengis.net/kml/2.2}Point')
                            
                            if name_elem is not None and point_elem is not None:
                                coords_elem = point_elem.find('.//{http://www.opengis.net/kml/2.2}coordinates')
                                if coords_elem is not None:
                                    coords = coords_elem.text.strip().split(',')
                                    if len(coords) >= 2:
                                        st.session_state.points_data.append({
                                            'name': name_elem.text or "Point importé",
                                            'lat': float(coords[1]),
                                            'lon': float(coords[0])
                                        })
                    
                    st.success("KML importé avec succès!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de l'import: {str(e)}")
    
    else:
        # Interface complète pour autres appareils
        st.title("🗺️ Générateur KML pour SDVFR")
        
        # Ici tu peux garder ton interface complète existante
        # ou importer le contenu du fichier original
        st.info("Interface complète - utilisez le fichier original pour toutes les fonctionnalités")

if __name__ == "__main__":
    main()