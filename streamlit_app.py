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

# Configuration minimale pour iOS 26
st.set_page_config(
    page_title="Générateur KML pour SDVFR",
    layout="wide"
)

# Configuration API chargée depuis config.py

# Version ultra-minimaliste pour iOS 26

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
WGS84_A = 6378137.0  # Demi-grand axe (m)
WGS84_F = 1/298.257223563  # Aplatissement
WGS84_B = WGS84_A * (1 - WGS84_F)  # Demi-petit axe

# Fonctions géodésiques haute précision (Vincenty)
def calculate_distance(lat1, lon1, lat2, lon2):
    """Distance Vincenty inverse - précision sub-métrique"""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    L = lon2_rad - lon1_rad
    U1 = math.atan((1 - WGS84_F) * math.tan(lat1_rad))
    U2 = math.atan((1 - WGS84_F) * math.tan(lat2_rad))
    
    sin_U1, cos_U1 = math.sin(U1), math.cos(U1)
    sin_U2, cos_U2 = math.sin(U2), math.cos(U2)
    
    lambda_val = L
    for _ in range(100):
        sin_lambda, cos_lambda = math.sin(lambda_val), math.cos(lambda_val)
        sin_sigma = math.sqrt((cos_U2 * sin_lambda) ** 2 + (cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lambda) ** 2)
        
        if sin_sigma == 0:
            return 0.0
        
        cos_sigma = sin_U1 * sin_U2 + cos_U1 * cos_U2 * cos_lambda
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_U1 * cos_U2 * sin_lambda / sin_sigma
        cos2_alpha = 1 - sin_alpha ** 2
        
        if cos2_alpha == 0:
            cos_2sigma_m = 0
        else:
            cos_2sigma_m = cos_sigma - 2 * sin_U1 * sin_U2 / cos2_alpha
        
        C = WGS84_F / 16 * cos2_alpha * (4 + WGS84_F * (4 - 3 * cos2_alpha))
        lambda_prev = lambda_val
        lambda_val = L + (1 - C) * WGS84_F * sin_alpha * (sigma + C * sin_sigma * (cos_2sigma_m + C * cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)))
        
        if abs(lambda_val - lambda_prev) < 1e-12:
            break
    
    u2 = cos2_alpha * (WGS84_A ** 2 - WGS84_B ** 2) / (WGS84_B ** 2)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    delta_sigma = B * sin_sigma * (cos_2sigma_m + B / 4 * (cos_sigma * (-1 + 2 * cos_2sigma_m ** 2) - B / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma ** 2) * (-3 + 4 * cos_2sigma_m ** 2)))
    
    return WGS84_B * A * (sigma - delta_sigma)

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Gisement initial Vincenty - précision sub-métrique"""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    L = lon2_rad - lon1_rad
    U1 = math.atan((1 - WGS84_F) * math.tan(lat1_rad))
    U2 = math.atan((1 - WGS84_F) * math.tan(lat2_rad))
    
    sin_U1, cos_U1 = math.sin(U1), math.cos(U1)
    sin_U2, cos_U2 = math.sin(U2), math.cos(U2)
    
    lambda_val = L
    for _ in range(100):
        sin_lambda, cos_lambda = math.sin(lambda_val), math.cos(lambda_val)
        sin_sigma = math.sqrt((cos_U2 * sin_lambda) ** 2 + (cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lambda) ** 2)
        
        if sin_sigma == 0:
            return 0.0
        
        cos_sigma = sin_U1 * sin_U2 + cos_U1 * cos_U2 * cos_lambda
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_U1 * cos_U2 * sin_lambda / sin_sigma
        cos2_alpha = 1 - sin_alpha ** 2
        
        if cos2_alpha == 0:
            cos_2sigma_m = 0
        else:
            cos_2sigma_m = cos_sigma - 2 * sin_U1 * sin_U2 / cos2_alpha
        
        C = WGS84_F / 16 * cos2_alpha * (4 + WGS84_F * (4 - 3 * cos2_alpha))
        lambda_prev = lambda_val
        lambda_val = L + (1 - C) * WGS84_F * sin_alpha * (sigma + C * sin_sigma * (cos_2sigma_m + C * cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)))
        
        if abs(lambda_val - lambda_prev) < 1e-12:
            break
    
    alpha1 = math.atan2(cos_U2 * sin_lambda, cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lambda)
    return (math.degrees(alpha1) + 360) % 360

def convert_calamar_to_gps(x_val, y_val, x_unit, y_unit):
    """Convertit des coordonnées Calamar en GPS"""
    calamar_points = np.array([
        [0.0, 0.0],
        [683.0, 921.0],
        [284.73, -398.51]
    ])
    
    gps_points = np.array([
        [44.52041351, -1.11661145],
        [44.523935, -1.130166],
        [44.51600897, -1.11683657]
    ])
    
    y_calamar = x_val if x_unit == "mL" else -x_val
    x_calamar = y_val if y_unit == "mD" else -y_val
    
    A = np.column_stack([calamar_points, np.ones(3)])
    lat_params = np.linalg.lstsq(A, gps_points[:, 0], rcond=None)[0]
    lon_params = np.linalg.lstsq(A, gps_points[:, 1], rcond=None)[0]
    
    result_lat = lat_params[0] * y_calamar + lat_params[1] * x_calamar + lat_params[2]
    result_lon = lon_params[0] * y_calamar + lon_params[1] * x_calamar + lon_params[2]
    
    return result_lat, result_lon

def calculate_circle_points(center_lat, center_lon, radius_km, num_segments, is_arc=False, start_angle_deg=0, end_angle_deg=360, close_arc=True):
    """Calcul de cercles avec précision Vincenty"""
    points = []
    center_point = {"lat": center_lat, "lon": center_lon}

    if is_arc:
        if end_angle_deg < start_angle_deg:
            end_angle_deg += 360
        
        # Pour les arcs fermés, ajouter le centre au début
        if close_arc:
            points.append((center_lon, center_lat))
        
        angle_range = end_angle_deg - start_angle_deg
        effective_num_segments = max(num_segments, int(abs(angle_range)))
        
        # Générer les points de l'arc
        for i in range(effective_num_segments + 1):
            angle_deg = start_angle_deg + (angle_range / effective_num_segments) * i
            if angle_deg > 360:
                angle_deg -= 360
            
            new_lat, new_lon = create_point_from_bearing_distance(center_point, radius_km, angle_deg)
            points.append((new_lon, new_lat))
        
        # Pour les arcs fermés, fermer vers le centre
        if close_arc:
            points.append((center_lon, center_lat))
    else:
        # Cercle complet
        for i in range(num_segments + 1):
            angle_deg = (360 / num_segments) * i
            new_lat, new_lon = create_point_from_bearing_distance(center_point, radius_km, angle_deg)
            points.append((new_lon, new_lat))
    return points

def calculate_rectangle_points(center_lat, center_lon, length_km, width_km, bearing_deg):
    """Calcul de rectangles avec précision Vincenty"""
    center_point = {"lat": center_lat, "lon": center_lon}
    half_length_km = length_km / 2
    half_width_km = width_km / 2
    
    corners_local = [
        (half_length_km, half_width_km),
        (half_length_km, -half_width_km),
        (-half_length_km, -half_width_km),
        (-half_length_km, half_width_km)
    ]
    
    rectangle_points = []

    for x_local, y_local in corners_local:
        dist_to_corner = math.sqrt(x_local**2 + y_local**2)
        angle_relative = math.degrees(math.atan2(y_local, x_local))
        absolute_bearing = (bearing_deg + angle_relative) % 360
        
        new_lat, new_lon = create_point_from_bearing_distance(center_point, dist_to_corner, absolute_bearing)
        rectangle_points.append((new_lon, new_lat))
    
    rectangle_points.append(rectangle_points[0])  # Fermer le rectangle
    return rectangle_points

def create_point_from_bearing_distance(start_point, distance_km, bearing_deg):
    """Formule directe Vincenty - précision sub-métrique"""
    lat1_rad = math.radians(start_point["lat"])
    lon1_rad = math.radians(start_point["lon"])
    alpha1_rad = math.radians(bearing_deg)
    s = distance_km * 1000  # Convertir en mètres
    
    sin_alpha1, cos_alpha1 = math.sin(alpha1_rad), math.cos(alpha1_rad)
    tan_U1 = (1 - WGS84_F) * math.tan(lat1_rad)
    cos_U1 = 1 / math.sqrt(1 + tan_U1 ** 2)
    sin_U1 = tan_U1 * cos_U1
    
    sigma1 = math.atan2(tan_U1, cos_alpha1)
    sin_alpha = cos_U1 * sin_alpha1
    cos2_alpha = 1 - sin_alpha ** 2
    u2 = cos2_alpha * (WGS84_A ** 2 - WGS84_B ** 2) / (WGS84_B ** 2)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    
    sigma = s / (WGS84_B * A)
    for _ in range(100):
        cos_2sigma_m = math.cos(2 * sigma1 + sigma)
        sin_sigma, cos_sigma = math.sin(sigma), math.cos(sigma)
        delta_sigma = B * sin_sigma * (cos_2sigma_m + B / 4 * (cos_sigma * (-1 + 2 * cos_2sigma_m ** 2) - B / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma ** 2) * (-3 + 4 * cos_2sigma_m ** 2)))
        sigma_prev = sigma
        sigma = s / (WGS84_B * A) + delta_sigma
        
        if abs(sigma - sigma_prev) < 1e-12:
            break
    
    tmp = sin_U1 * sin_sigma - cos_U1 * cos_sigma * cos_alpha1
    lat2_rad = math.atan2(sin_U1 * cos_sigma + cos_U1 * sin_sigma * cos_alpha1, (1 - WGS84_F) * math.sqrt(sin_alpha ** 2 + tmp ** 2))
    lambda_val = math.atan2(sin_sigma * sin_alpha1, cos_U1 * cos_sigma - sin_U1 * sin_sigma * cos_alpha1)
    C = WGS84_F / 16 * cos2_alpha * (4 + WGS84_F * (4 - 3 * cos2_alpha))
    L = lambda_val - (1 - C) * WGS84_F * sin_alpha * (sigma + C * sin_sigma * (cos_2sigma_m + C * cos_sigma * (-1 + 2 * cos_2sigma_m ** 2)))
    lon2_rad = (lon1_rad + L + 3 * math.pi) % (2 * math.pi) - math.pi
    
    return math.degrees(lat2_rad), math.degrees(lon2_rad)

def parse_kml_file(kml_content):
    """Parse un fichier KML et extrait les objets avec leurs styles"""
    try:
        root = ET.fromstring(kml_content)
        
        # Namespaces KML
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        points = []
        lines = []
        polygons = []
        
        # Fonction pour extraire les styles
        def extract_style(placemark):
            color = "rouge"
            width = 2
            
            # Chercher le style inline ou référencé
            style_elem = placemark.find('.//kml:Style', ns)
            
            # Si pas de style inline, chercher styleUrl
            if style_elem is None:
                style_url_elem = placemark.find('kml:styleUrl', ns)
                if style_url_elem is not None:
                    style_id = style_url_elem.text.replace('#', '')
                    # Chercher le style dans le document
                    style_elem = root.find(f'.//kml:Style[@id="{style_id}"]', ns)
            
            if style_elem is not None:
                # Couleur de ligne
                line_style = style_elem.find('.//kml:LineStyle/kml:color', ns)
                if line_style is not None:
                    kml_color = line_style.text.strip().lower()
                    
                    # Mapping direct des couleurs KML courantes
                    kml_color_map = {
                        'ff0000ff': 'rouge',     # Rouge
                        'ffff0000': 'bleu',      # Bleu  
                        'ff00ff00': 'vert',      # Vert
                        'ff008000': 'vert',      # Vert foncé
                        'ffffff00': 'jaune',     # Jaune
                        'ffff8000': 'orange',    # Orange
                        'ff00ffff': 'cyan',      # Cyan
                        'ffff00ff': 'magenta',   # Magenta
                        'ff000000': 'noir',      # Noir
                        'ffffffff': 'blanc',     # Blanc
                    }
                    
                    if kml_color in kml_color_map:
                        color = kml_color_map[kml_color]
                    else:
                        # Fallback: analyse RGB
                        try:
                            if len(kml_color) == 8:
                                b = int(kml_color[2:4], 16)
                                g = int(kml_color[4:6], 16) 
                                r = int(kml_color[6:8], 16)
                                
                                if g > r and g > b and g > 100:
                                    color = "vert"
                                elif r > g and r > b and r > 100:
                                    color = "rouge"
                                elif b > r and b > g and b > 100:
                                    color = "bleu"
                        except ValueError:
                            pass
                
                # Épaisseur de ligne
                width_elem = style_elem.find('.//kml:LineStyle/kml:width', ns)
                if width_elem is not None:
                    try:
                        width = max(1, int(float(width_elem.text.strip())))
                    except:
                        width = 2
            
            return color, width
        
        # Extraire les points (Placemark avec Point)
        for placemark in root.findall('.//kml:Placemark', ns):
            name_elem = placemark.find('kml:name', ns)
            name = name_elem.text if name_elem is not None else "Point sans nom"
            
            desc_elem = placemark.find('kml:description', ns)
            description = desc_elem.text if desc_elem is not None else ""
            
            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords = point_elem.text.strip().split(',')
                if len(coords) >= 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    points.append({
                        "type": "Point", "name": name, "lat": lat, "lon": lon, 
                        "description": description
                    })
            
            # Extraire les lignes (LineString)
            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords_list = []
                for coord_pair in coords_text.split():
                    if ',' in coord_pair:
                        parts = coord_pair.split(',')
                        if len(parts) >= 2:
                            coords_list.append((float(parts[0]), float(parts[1])))
                
                if len(coords_list) >= 2:
                    color, width = extract_style(placemark)
                    lines.append({
                        "type": "Ligne", "name": name, "points": coords_list,
                        "description": description, "color": color, "width": width
                    })
            
            # Extraire les polygones
            poly_elem = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if poly_elem is not None:
                coords_text = poly_elem.text.strip()
                coords_list = []
                for coord_pair in coords_text.split():
                    if ',' in coord_pair:
                        parts = coord_pair.split(',')
                        if len(parts) >= 2:
                            coords_list.append((float(parts[0]), float(parts[1])))
                
                if len(coords_list) >= 3:
                    # Calculer le centre approximatif
                    lats = [coord[1] for coord in coords_list]
                    lons = [coord[0] for coord in coords_list]
                    center_lat = sum(lats) / len(lats)
                    center_lon = sum(lons) / len(lons)
                    
                    color, width = extract_style(placemark)
                    polygons.append({
                        "type": "Polygone", "name": name, "points": coords_list,
                        "description": description, "color": color, "width": width,
                        "fill": False, "center_lat": center_lat, "center_lon": center_lon
                    })
        
        return points, lines, polygons
    
    except Exception as e:
        st.error(f"Erreur lors du parsing KML: {e}")
        return [], [], []

def load_reference_kml():
    """Charge le fichier KML de référence s'il existe"""
    reference_path = "reference.kml"
    if os.path.exists(reference_path):
        try:
            with open(reference_path, 'r', encoding='utf-8') as f:
                kml_content = f.read()
            points, lines, polygons = parse_kml_file(kml_content)
            st.session_state.reference_data = {
                'points': points,
                'lines': lines, 
                'polygons': polygons
            }
            return True
        except Exception as e:
            st.error(f"Erreur chargement référence: {e}")
    return False

def load_kml_data(points, lines, polygons):
    """Charge les données KML dans la session"""
    st.session_state.points_data.extend(points)
    st.session_state.lines_data.extend(lines)
    st.session_state.rectangles_data.extend(polygons)
    
    # Réinitialiser les listes temporaires
    st.session_state.current_line_points = []
    st.session_state.current_polygon_points = []

def generate_kml():
    kml = simplekml.Kml()
    
    color_map = {
        "rouge": simplekml.Color.red, "vert": simplekml.Color.green, "bleu": simplekml.Color.blue,
        "jaune": simplekml.Color.yellow, "orange": simplekml.Color.orange, "cyan": simplekml.Color.cyan, 
        "magenta": simplekml.Color.magenta, "noir": simplekml.Color.black, "blanc": simplekml.Color.white
    }

    if st.session_state.points_data:
        points_folder = kml.newfolder(name="Points Générés")
        for p_data in st.session_state.points_data:
            p = points_folder.newpoint(name=p_data['name'], coords=[(p_data['lon'], p_data['lat'])])
            if p_data.get('description'):
                p.description = p_data['description']

    if st.session_state.lines_data:
        lines_folder = kml.newfolder(name="Lignes Générées")
        for l_data in st.session_state.lines_data:
            ls = lines_folder.newlinestring(name=l_data['name'], coords=l_data['points'])
            if l_data.get('description'):
                ls.description = l_data['description']
            ls.style.linestyle.width = l_data['width']
            ls.style.linestyle.color = color_map.get(l_data['color'], simplekml.Color.red)

    if st.session_state.circles_data:
        # Séparer arcs ouverts et cercles/arcs fermés
        open_arcs = [c for c in st.session_state.circles_data if c.get('type') == 'Arc' and not c.get('close_arc', True)]
        closed_shapes = [c for c in st.session_state.circles_data if not (c.get('type') == 'Arc' and not c.get('close_arc', True))]
        
        # Arcs ouverts dans le dossier lignes
        if open_arcs:
            if not st.session_state.lines_data:
                lines_folder = kml.newfolder(name="Lignes Générées")
            for c_data in open_arcs:
                if 'points' in c_data:
                    line = lines_folder.newlinestring(name=c_data['name'], coords=c_data['points'])
                    if c_data.get('description'):
                        line.description = c_data['description']
                    line.style.linestyle.width = c_data.get('width', 2)
                    line.style.linestyle.color = color_map.get(c_data.get('color', 'rouge'), simplekml.Color.red)
        
        # Cercles et arcs fermés
        if closed_shapes:
            circles_folder = kml.newfolder(name="Cercles et Arcs Fermés")
            for c_data in closed_shapes:
                if 'points' in c_data:
                    # Créer un polygone avec style explicite
                    poly = circles_folder.newpolygon(name=c_data['name'], outerboundaryis=c_data['points'])
                    if c_data.get('description'):
                        poly.description = c_data['description']
                    
                    # Style de ligne
                    poly.style.linestyle.width = c_data.get('width', 2)
                    poly.style.linestyle.color = color_map.get(c_data.get('color', 'rouge'), simplekml.Color.red)
                    
                    # Style de remplissage
                    if c_data.get('fill', False):
                        base_color = color_map.get(c_data.get('color', 'rouge'), simplekml.Color.red)
                        poly.style.polystyle.color = simplekml.Color.changealphaint(150, base_color)
                        poly.style.polystyle.fill = 1
                    else:
                        poly.style.polystyle.fill = 0
                        poly.style.polystyle.outline = 1  # Forcer l'affichage du contour

    if st.session_state.rectangles_data:
        rectangles_folder = kml.newfolder(name="Rectangles Générés")
        for r_data in st.session_state.rectangles_data:
            poly = rectangles_folder.newpolygon(name=r_data['name'], outerboundaryis=r_data['points'])
            poly.style.linestyle.width = r_data.get('width', 2)
            poly.style.linestyle.color = color_map.get(r_data.get('color', 'rouge'), simplekml.Color.red)
            
            if r_data.get('fill', False):
                base_color = color_map.get(r_data.get('color', 'rouge'), simplekml.Color.red)
                poly.style.polystyle.color = simplekml.Color.changealphaint(150, base_color)
                poly.style.polystyle.fill = 1
            else:
                poly.style.polystyle.fill = 0

    return kml

def convert_kml_to_mbtiles(kml_content, min_zoom=0, max_zoom=14, name="converted_tiles", preserve_properties=True, simplification=0.0):
    """Convertit un KML en MBTiles via l'API FastAPI avec contrôle de la fidélité"""
    try:
        # Créer un fichier temporaire pour le KML
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kml', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(kml_content)
            tmp_file_path = tmp_file.name
        
        # Préparer la requête à l'API
        with open(tmp_file_path, 'rb') as f:
            files = {'file': (f'{name}.kml', f, 'application/vnd.google-earth.kml+xml')}
            data = {
                'min_zoom': min_zoom,
                'max_zoom': max_zoom,
                'name': name,
                'preserve_properties': preserve_properties,
                'simplification': simplification
            }
            
            # Envoyer la requête à l'API
            response = requests.post(
                f"{get_api_url()}/convert-to-mbtiles",
                files=files,
                data=data,
                timeout=API_TIMEOUT
            )
        
        # Nettoyer le fichier temporaire
        os.unlink(tmp_file_path)
        
        if response.status_code == 200:
            return response.content
        else:
            error_msg = response.json().get('detail', 'Erreur inconnue') if response.headers.get('content-type') == 'application/json' else response.text
            raise Exception(f"Erreur API: {error_msg}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur de connexion à l'API: {str(e)}")
    except Exception as e:
        raise Exception(f"Erreur lors de la conversion: {str(e)}")





def process_tiff_overlay(tiff_path):
    """Traite un fichier TIFF géoréférencé pour l'overlay"""
    if not RASTERIO_AVAILABLE:
        return None
    
    try:
        with rasterio.open(tiff_path) as src:
            bounds = src.bounds
            crs = src.crs
            
            if crs != 'EPSG:4326':
                bounds = transform_bounds(crs, 'EPSG:4326', *bounds)
            
            img_array = src.read()
            
            if img_array.shape[0] == 3:  # RGB
                img = Image.fromarray(np.transpose(img_array, (1, 2, 0)), mode='RGB')
            elif img_array.shape[0] == 4:  # RGBA
                img = Image.fromarray(np.transpose(img_array, (1, 2, 0)), mode='RGBA')
            else:
                img = Image.fromarray(img_array[0], mode='L')
            
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_b64 = base64.b64encode(buffer.getvalue()).decode()
            
            return {
                'bounds': [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                'image': f"data:image/png;base64,{img_b64}",
                'opacity': 0.7
            }
    except Exception as e:
        st.error(f"Erreur TIFF: {e}")
        return None

def create_map():
    # Calculer le centre de la carte
    all_lats, all_lons = [], []
    
    for point in st.session_state.points_data:
        all_lats.append(point['lat'])
        all_lons.append(point['lon'])
    
    for line in st.session_state.lines_data:
        for lon, lat in line['points']:
            all_lats.append(lat)
            all_lons.append(lon)
    
    for circle in st.session_state.circles_data:
        if 'points' in circle:
            for lon, lat in circle['points']:
                all_lats.append(lat)
                all_lons.append(lon)
    
    for rect in st.session_state.rectangles_data:
        if 'points' in rect:
            for lon, lat in rect['points']:
                all_lats.append(lat)
                all_lons.append(lon)
    
    if all_lats and all_lons:
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)
    else:
        center_lat, center_lon = 44.52, -1.12
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    
    # Ajouter les fonds de carte satellite
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite (Esri)',
        overlay=False,
        control=True
    ).add_to(m)
    
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google',
        name='Satellite (Google)',
        overlay=False,
        control=True
    ).add_to(m)
    
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Plan (Esri)',
        overlay=False,
        control=True
    ).add_to(m)
    
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google',
        name='Hybride (Google)',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Ajouter OpenTopoMap pour le relief
    folium.TileLayer(
        tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attr='OpenTopoMap',
        name='Relief (OpenTopo)',
        overlay=False,
        control=True
    ).add_to(m)
    

    
    # Ajouter un marqueur temporaire si une position a été cliquée
    if 'clicked_position' in st.session_state and st.session_state.clicked_position:
        folium.Marker(
            st.session_state.clicked_position,
            popup="📍 Position cliquée",
            tooltip=f"Clic: {st.session_state.clicked_position[0]:.6f}, {st.session_state.clicked_position[1]:.6f}",
            icon=folium.Icon(color='red', icon='star')
        ).add_to(m)
    

    

    
    # Ajouter les tuiles personnalisées
    for tile in st.session_state.custom_tiles:
        if tile['type'] == 'tiff' and RASTERIO_AVAILABLE:
            overlay_data = process_tiff_overlay(tile['path'])
            if overlay_data:
                folium.raster_layers.ImageOverlay(
                    image=overlay_data['image'],
                    bounds=overlay_data['bounds'],
                    opacity=overlay_data['opacity'],
                    name=tile['name'],
                    show=True
                ).add_to(m)
    
    # Ajouter le contrôle des couches (toujours présent maintenant)
    folium.LayerControl().add_to(m)
    
    # Ajouter les points de référence si activés
    if st.session_state.show_reference:
        for point in st.session_state.reference_data['points']:
            folium.Marker(
                [point['lat'], point['lon']],
                popup=f"📍 REF: {point['name']}",
                tooltip=f"Référence: {point['name']}",
                icon=folium.Icon(color='blue', icon='star')
            ).add_to(m)
    
    # Ajouter les points utilisateur
    for point in st.session_state.points_data:
        folium.Marker(
            [point['lat'], point['lon']],
            popup=point['name'],
            tooltip=f"{point['name']}: {point['lat']:.4f}, {point['lon']:.4f}"
        ).add_to(m)
    
    # Ajouter les lignes
    color_mapping = {
        'rouge': 'red', 'vert': 'green', 'bleu': 'blue', 'jaune': 'yellow',
        'orange': 'orange', 'cyan': 'cyan', 'magenta': 'magenta', 'noir': 'black', 'blanc': 'white'
    }
    
    for line in st.session_state.lines_data:
        coords = [[lat, lon] for lon, lat in line['points']]
        line_color = color_mapping.get(line.get('color', 'rouge'), 'red')
        folium.PolyLine(
            coords,
            color=line_color,
            weight=line.get('width', 2),
            popup=line['name'],
            tooltip=f"Ligne: {line['name']}"
        ).add_to(m)
    
    # Ajouter les cercles
    for circle in st.session_state.circles_data:
        if 'points' in circle:
            coords = [[lat, lon] for lon, lat in circle['points']]
            circle_color = color_mapping.get(circle.get('color', 'rouge'), 'red')
            
            # Utiliser PolyLine pour les arcs ouverts, Polygon pour les arcs fermés et cercles
            if circle.get('type') == 'Arc' and not circle.get('close_arc', True):
                folium.PolyLine(
                    coords,
                    color=circle_color,
                    weight=circle.get('width', 2),
                    popup=circle['name']
                ).add_to(m)
            else:
                folium.Polygon(
                    coords,
                    color=circle_color,
                    weight=circle.get('width', 2),
                    fill=circle.get('fill', False),
                    popup=circle['name']
                ).add_to(m)
    
    # Ajouter les rectangles
    for rect in st.session_state.rectangles_data:
        if 'points' in rect:
            coords = [[lat, lon] for lon, lat in rect['points']]
            rect_color = color_mapping.get(rect.get('color', 'rouge'), 'red')
            folium.Polygon(
                coords,
                color=rect_color,
                weight=rect.get('width', 2),
                fill=rect.get('fill', False),
                popup=rect['name']
            ).add_to(m)
            
            # Ajouter la flèche d'orientation si demandée
            if rect.get('add_arrow', False) and 'center_lat' in rect and 'bearing_deg' in rect:
                center_lat = rect['center_lat']
                center_lon = rect['center_lon']
                bearing = rect['bearing_deg']
                length_km = rect.get('length_km', 0.001)
                width_km = rect.get('width_km', 0.001)
                
                R = 6371.0
                bearing_rad = math.radians(bearing)
                lat_rad = math.radians(center_lat)
                lon_rad = math.radians(center_lon)
                
                # Point de départ : milieu du côté avant (orienté vers le cap)
                front_offset_km = length_km / 2
                arrow_start_lat_rad = math.asin(math.sin(lat_rad) * math.cos(front_offset_km / R) +
                                              math.cos(lat_rad) * math.sin(front_offset_km / R) * math.cos(bearing_rad))
                
                arrow_start_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(front_offset_km / R) * math.cos(lat_rad),
                                                         math.cos(front_offset_km / R) - math.sin(lat_rad) * math.sin(arrow_start_lat_rad))
                
                arrow_start_lat = math.degrees(arrow_start_lat_rad)
                arrow_start_lon = math.degrees(arrow_start_lon_rad)
                
                # Point de fin de la flèche (longueur = moitié de la largeur)
                arrow_length_km = width_km / 2
                arrow_end_lat_rad = math.asin(math.sin(math.radians(arrow_start_lat)) * math.cos(arrow_length_km / R) +
                                            math.cos(math.radians(arrow_start_lat)) * math.sin(arrow_length_km / R) * math.cos(bearing_rad))
                
                arrow_end_lon_rad = math.radians(arrow_start_lon) + math.atan2(math.sin(bearing_rad) * math.sin(arrow_length_km / R) * math.cos(math.radians(arrow_start_lat)),
                                                                             math.cos(arrow_length_km / R) - math.sin(math.radians(arrow_start_lat)) * math.sin(arrow_end_lat_rad))
                
                arrow_end_lat = math.degrees(arrow_end_lat_rad)
                arrow_end_lon = math.degrees(arrow_end_lon_rad)
                
                # Dessiner la flèche
                folium.PolyLine(
                    [[arrow_start_lat, arrow_start_lon], [arrow_end_lat, arrow_end_lon]],
                    color=rect_color,
                    weight=rect.get('width', 2),
                    popup=f"Orientation {rect['name']}: {bearing}°"
                ).add_to(m)
                

    
    return m

# Interface principale
st.markdown("<h1 style='margin-top: 0px; padding-top: 0px;'>🗺️ Générateur KML pour SDVFR</h1>", unsafe_allow_html=True)

# Navigation par onglets
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📁 Import / Export KML", "📍 Points", "📏 Lignes", "⭕ Cercles/Arcs", "🔷 Polygones", "🔧 Divers", "🗺️ Visualisation"])



# ONGLET GESTION KML
with tab1:
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📤 Importer un fichier KML")
        
        uploaded_file = st.file_uploader("Sélectionnez un fichier KML", type=['kml'], key="main_upload")
        
        if uploaded_file is not None:
            kml_content = uploaded_file.read().decode('utf-8')
            points, lines, polygons = parse_kml_file(kml_content)
            
            st.write(f"**Contenu détecté:**")
            st.write(f"- 📍 {len(points)} points")
            st.write(f"- 📏 {len(lines)} lignes")
            st.write(f"- 🔷 {len(polygons)} polygones")
            
            if points or lines or polygons:
                import_mode = st.radio(
                    "Mode d'importation:",
                    ["Ajouter aux données existantes", "Remplacer toutes les données"]
                )
                
                if st.button("✅ Importer le KML", key="main_import"):
                    if import_mode == "Remplacer toutes les données":
                        st.session_state.points_data = []
                        st.session_state.lines_data = []
                        st.session_state.circles_data = []
                        st.session_state.rectangles_data = []
                    
                    load_kml_data(points, lines, polygons)
                    st.success(f"KML importé avec succès! ({len(points + lines + polygons)} objets)")
                    st.rerun()
            else:
                st.warning("Aucun objet valide trouvé dans le fichier KML")
    
    with col2:
        st.subheader("📥 Exporter les données")
        
        total_objects = len(st.session_state.points_data) + len(st.session_state.lines_data) + len(st.session_state.circles_data) + len(st.session_state.rectangles_data)
        
        if total_objects > 0:
            st.write(f"**Données actuelles:**")
            st.write(f"- 📍 {len(st.session_state.points_data)} points")
            st.write(f"- 📏 {len(st.session_state.lines_data)} lignes")
            st.write(f"- ⭕ {len(st.session_state.circles_data)} cercles/arcs")
            st.write(f"- 🔷 {len(st.session_state.rectangles_data)} polygones")
            
            filename = st.text_input("Nom du fichier KML", value="export_sdvfr", placeholder="Nom sans extension")
            
            col_kml, col_mbtiles = st.columns(2)
            
            with col_kml:
                if st.button("📥 Générer KML"):
                    clean_filename = filename.replace('.kml', '') if filename else "export_sdvfr"
                    
                    kml = generate_kml()
                    kml_str = kml.kml()
                    st.download_button(
                        label="💾 Télécharger le KML",
                        data=kml_str,
                        file_name=f"{clean_filename}.kml",
                        mime="application/vnd.google-earth.kml+xml"
                    )
            
            with col_mbtiles:
                # Vérifier si l'API est configurée
                if not is_api_configured():
                    st.warning("⚠️ API non configurée")
                    st.button("🗺️ Générer MBTiles", disabled=True)
                elif st.button("🗺️ Générer MBTiles"):
                    clean_filename = filename.replace('.kml', '') if filename else "export_sdvfr"
                    
                    with st.spinner("Conversion en cours via Tippecanoe..."):
                        try:
                            kml = generate_kml()
                            kml_str = kml.kml()
                            
                            # Paramètres de conversion
                            min_zoom = st.session_state.get('mbtiles_min_zoom', 0)
                            max_zoom = st.session_state.get('mbtiles_max_zoom', 14)
                            preserve_props = st.session_state.get('preserve_props', True)
                            simplif_level = st.session_state.get('simplification_select', (0.0, "Aucune (fidélité maximale)"))
                            if isinstance(simplif_level, tuple):
                                simplif_level = simplif_level[0]
                            
                            mbtiles_data = convert_kml_to_mbtiles(
                                kml_str, 
                                min_zoom=min_zoom, 
                                max_zoom=max_zoom, 
                                name=clean_filename,
                                preserve_properties=preserve_props,
                                simplification=simplif_level
                            )
                            
                            st.download_button(
                                label="💾 Télécharger MBTiles",
                                data=mbtiles_data,
                                file_name=f"{clean_filename}.mbtiles",
                                mime="application/octet-stream"
                            )
                            st.success("✅ MBTiles généré avec succès!")
                            
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la génération MBTiles: {str(e)}")
                            st.info("💡 Vérifiez que l'API de conversion est accessible")
            
            # Paramètres MBTiles
            with st.expander("⚙️ Paramètres MBTiles"):
                col_min, col_max = st.columns(2)
                with col_min:
                    min_zoom = st.slider("Zoom minimum", 0, 18, 0, key="mbtiles_min_zoom")
                with col_max:
                    max_zoom = st.slider("Zoom maximum", 0, 18, 14, key="mbtiles_max_zoom")
                
                st.markdown("**🎯 Fidélité de conversion**")
                preserve_properties = st.checkbox("Préserver toutes les propriétés KML", value=True, key="preserve_props")
                
                simplification = st.selectbox(
                    "Simplification géométrique",
                    [(0.0, "Aucune (fidélité maximale)"), 
                     (0.1, "Très faible"), 
                     (0.5, "Faible"), 
                     (1.0, "Modérée"), 
                     (2.0, "Élevée")],
                    format_func=lambda x: x[1],
                    key="simplification_select"
                )[0]
                
                st.info(f"📊 Niveaux de zoom: {min_zoom} à {max_zoom}")
                if simplification == 0.0:
                    st.success("🎯 Configuration pour fidélité maximale")
                else:
                    st.warning(f"⚠️ Simplification activée: {simplification}")
                st.caption("💡 Fidélité maximale = fichier plus volumineux mais plus précis")
        else:
            st.info("Aucune donnée à exporter. Créez d'abord des objets.")
            st.info("💡 **Format KML :** Compatible Google Earth et SDVFR classique")
    
    # Aperçu des données
    if total_objects > 0:
        st.markdown("---")
        st.subheader("👁️ Aperçu des données")
        
        # Créer un DataFrame avec tous les objets
        all_objects = []
        
        for point in st.session_state.points_data:
            all_objects.append({
                "Type": "Point",
                "Nom": point['name'],
                "Détails": f"Lat: {point['lat']:.4f}, Lon: {point['lon']:.4f}",
                "Description": point.get('description', '')
            })
        
        for line in st.session_state.lines_data:
            all_objects.append({
                "Type": "Ligne",
                "Nom": line['name'],
                "Détails": f"{len(line['points'])} points, {line['color']}",
                "Description": line.get('description', '')
            })
        
        for circle in st.session_state.circles_data:
            radius_display = circle['radius_km'] / 1.852 if circle['radius_unit'] == 'nautiques' else circle['radius_km'] * 1000
            unit_display = "NM" if circle['radius_unit'] == 'nautiques' else "m"
            all_objects.append({
                "Type": "Cercle/Arc",
                "Nom": circle['name'],
                "Détails": f"R={radius_display:.2f}{unit_display}, {circle['color']}",
                "Description": circle.get('description', '')
            })
        
        for rect in st.session_state.rectangles_data:
            if 'length_km' in rect:
                all_objects.append({
                    "Type": "Rectangle",
                    "Nom": rect['name'],
                    "Détails": f"{rect['length_km']*1000:.0f}m x {rect['width_km']*1000:.0f}m",
                    "Description": rect.get('description', '')
                })
            else:
                all_objects.append({
                    "Type": "Polygone",
                    "Nom": rect['name'],
                    "Détails": f"{len(rect['points'])} points",
                    "Description": rect.get('description', '')
                })
        
        if all_objects:
            df = pd.DataFrame(all_objects)
            st.dataframe(df, use_container_width=True)

# ONGLET POINTS
with tab2:
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Ajouter un point individuel")
        
        point_name = st.text_input("Nom du point")
        coord_format = st.selectbox("Format coordonnées", 
                                   ["Degrés décimaux", "Degrés Minutes", "Degrés Minutes Secondes", "Calamar"])
        
        if coord_format == "Degrés décimaux":
            lat_str = st.text_input("Latitude (ex: 44.5)")
            lon_str = st.text_input("Longitude (ex: -1.65)")
            if lat_str and lon_str:
                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                except ValueError:
                    st.error("Coordonnées invalides")
                    lat, lon = None, None
            else:
                lat, lon = None, None
            if lat and lon:
                try:
                    lat = float(lat)
                    lon = float(lon)
                except ValueError:
                    st.error("Coordonnées invalides")
                    lat, lon = None, None
            else:
                lat, lon = None, None
        
        elif coord_format == "Calamar":
            col_x, col_y = st.columns(2)
            with col_x:
                x_val = st.number_input("Axe Y", value=0.0, key="points_calamar_x")
                x_unit = st.selectbox("Unité Y", ["mL", "mC"], key="points_calamar_x_unit")
            with col_y:
                y_val = st.number_input("Axe X", value=0.0, key="points_calamar_y")
                y_unit = st.selectbox("Unité X", ["mD", "mG"], key="points_calamar_y_unit")
            
            lat, lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
            st.info(f"Coordonnées GPS: {lat:.6f}, {lon:.6f}")
        
        elif coord_format == "Degrés Minutes":
            # Latitude sur une ligne
            col_lat_deg, col_lat_min, col_lat_dir = st.columns([2, 2, 1])
            with col_lat_deg:
                lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="points_dm_lat_deg")
            with col_lat_min:
                lat_min = st.number_input("Lat '", value=31.2, min_value=0.0, max_value=59.999, format="%.3f", key="points_dm_lat_min")
            with col_lat_dir:
                lat_dir = st.selectbox("N/S", ["N", "S"], key="points_dm_lat_dir")
            
            # Longitude sur une ligne
            col_lon_deg, col_lon_min, col_lon_dir = st.columns([2, 2, 1])
            with col_lon_deg:
                lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="points_dm_lon_deg")
            with col_lon_min:
                lon_min = st.number_input("Lon '", value=7.2, min_value=0.0, max_value=59.999, format="%.3f", key="points_dm_lon_min")
            with col_lon_dir:
                lon_dir = st.selectbox("E/W", ["E", "W"], key="points_dm_lon_dir")
            
            lat = lat_deg + lat_min/60
            lon = lon_deg + lon_min/60
            if lat_dir == 'S': lat = -lat
            if lon_dir == 'W': lon = -lon
        
        else:  # DMS
            # Latitude sur une ligne
            col_lat_deg, col_lat_min, col_lat_sec, col_lat_dir = st.columns([2, 2, 2, 1])
            with col_lat_deg:
                lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="points_dms_lat_deg")
            with col_lat_min:
                lat_min = st.number_input("Lat '", value=31, min_value=0, max_value=59, key="points_dms_lat_min")
            with col_lat_sec:
                lat_sec = st.number_input("Lat \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="points_dms_lat_sec")
            with col_lat_dir:
                lat_dir = st.selectbox("N/S", ["N", "S"], key="points_dms_lat_dir")
            
            # Longitude sur une ligne
            col_lon_deg, col_lon_min, col_lon_sec, col_lon_dir = st.columns([2, 2, 2, 1])
            with col_lon_deg:
                lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="points_dms_lon_deg")
            with col_lon_min:
                lon_min = st.number_input("Lon '", value=7, min_value=0, max_value=59, key="points_dms_lon_min")
            with col_lon_sec:
                lon_sec = st.number_input("Lon \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="points_dms_lon_sec")
            with col_lon_dir:
                lon_dir = st.selectbox("E/W", ["E", "W"], key="points_dms_lon_dir")
            
            lat = lat_deg + lat_min/60 + lat_sec/3600
            lon = lon_deg + lon_min/60 + lon_sec/3600
            if lat_dir == 'S': lat = -lat
            if lon_dir == 'W': lon = -lon
        
        if st.button("➕ Ajouter Point", use_container_width=True):
            if point_name and not any(p['name'] == point_name for p in st.session_state.points_data):
                try:
                    if coord_format == "Calamar":
                        lat, lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
                    st.session_state.points_data.append({
                        "type": "Point", "name": point_name, "lat": lat, "lon": lon, "description": ""
                    })
                    st.success(f"Point '{point_name}' ajouté!")
                    st.rerun()
                except (ValueError, NameError):
                    st.error("Coordonnées invalides")
            else:
                st.error("Nom requis et unique")
    
    with col2:
        st.subheader("Point par relèvement/distance")
        
        if st.session_state.points_data:
            start_point_name = st.selectbox("Point de départ", 
                                          [p['name'] for p in st.session_state.points_data])
            new_point_name = st.text_input("Nom du nouveau point")
            
            col_dist, col_bear = st.columns(2)
            with col_dist:
                distance_val = st.number_input("Distance", value=1.0, min_value=0.1, key="points_distance")
                distance_unit = st.selectbox("Unité", ["mètres", "nautiques"], key="points_distance_unit")
            with col_bear:
                bearing_deg = st.number_input("Gisement (degrés)", value=0.0, min_value=0.0, max_value=359.9, key="points_bearing")
            
            if st.button("🎯 Créer Point", use_container_width=True):
                if new_point_name and start_point_name and not any(p['name'] == new_point_name for p in st.session_state.points_data):
                    start_point = next(p for p in st.session_state.points_data if p['name'] == start_point_name)
                    distance_km = distance_val * 1.852 if distance_unit == "nautiques" else distance_val / 1000
                    
                    new_lat, new_lon = create_point_from_bearing_distance(start_point, distance_km, bearing_deg)
                    
                    st.session_state.points_data.append({
                        "type": "Point", "name": new_point_name, "lat": new_lat, "lon": new_lon,
                        "description": f"Généré depuis {start_point_name}"
                    })
                    st.success(f"Point '{new_point_name}' créé!")
                    st.rerun()
                else:
                    st.error("Nom requis et unique")
        else:
            st.info("Créez d'abord un point de référence")
        
        st.markdown("---")
        st.subheader("Import en masse")
        
        # Import via fichier Excel/CSV
        uploaded_points_file = st.file_uploader(
            "Fichier Excel/CSV avec points", 
            type=['xlsx', 'xls', 'csv'],
            key="points_mass_import"
        )
        
        if uploaded_points_file is not None:
            try:
                if uploaded_points_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_points_file)
                else:
                    df = pd.read_excel(uploaded_points_file)
                
                st.write("**Aperçu du fichier:**")
                st.dataframe(df.head(), use_container_width=True)
                
                # Mapping des colonnes
                st.write("**Correspondance des colonnes:**")
                col_name = st.selectbox("Colonne nom", df.columns, key="mass_col_name")
                col_lat = st.selectbox("Colonne latitude", df.columns, key="mass_col_lat")
                col_lon = st.selectbox("Colonne longitude", df.columns, key="mass_col_lon")
                
                # Colonne description optionnelle
                col_desc = st.selectbox("Colonne description (optionnel)", [""] + list(df.columns), key="mass_col_desc")
                
                if st.button("📥 Importer tous les points", use_container_width=True):
                    imported_count = 0
                    errors = []
                    
                    for idx, row in df.iterrows():
                        try:
                            name = str(row[col_name]).strip()
                            lat = float(row[col_lat])
                            lon = float(row[col_lon])
                            desc = str(row[col_desc]).strip() if col_desc and col_desc in row else ""
                            
                            # Vérifier si le point existe déjà
                            if not any(p['name'] == name for p in st.session_state.points_data):
                                st.session_state.points_data.append({
                                    "type": "Point", "name": name, "lat": lat, "lon": lon, 
                                    "description": desc
                                })
                                imported_count += 1
                            else:
                                errors.append(f"Point '{name}' existe déjà")
                        except Exception as e:
                            errors.append(f"Ligne {idx+1}: {str(e)}")
                    
                    if imported_count > 0:
                        st.success(f"✅ {imported_count} points importés!")
                    if errors:
                        st.warning(f"⚠️ {len(errors)} erreurs:")
                        for error in errors[:5]:  # Afficher max 5 erreurs
                            st.caption(f"• {error}")
                    
                    if imported_count > 0:
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Erreur lors de la lecture du fichier: {e}")
    
    # Liste des points existants
    if st.session_state.points_data:
        st.markdown("---")
        st.subheader("Points existants")
        df_points = pd.DataFrame(st.session_state.points_data)
        st.dataframe(df_points[['name', 'lat', 'lon', 'description']], use_container_width=True)
        
        # Suppression de points
        point_to_delete = st.selectbox("Supprimer un point", 
                                     [""] + [p['name'] for p in st.session_state.points_data], key="points_delete_select")
        if point_to_delete and st.button("🗑️ Supprimer"):
            st.session_state.points_data = [p for p in st.session_state.points_data if p['name'] != point_to_delete]
            st.success(f"Point '{point_to_delete}' supprimé!")
            st.rerun()

# ONGLET LIGNES
with tab3:
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Points disponibles")
        if st.session_state.points_data:
            st.write("Cliquez sur un point pour l'ajouter à la ligne :")
            for i, point in enumerate(st.session_state.points_data):
                col_point, col_add = st.columns([3, 1])
                with col_point:
                    st.write(f"**{point['name']}** - {point['lat']:.4f}, {point['lon']:.4f}")
                with col_add:
                    if st.button("➕", key=f"add_line_{i}_{point['name']}"):
                        if point not in st.session_state.current_line_points:
                            st.session_state.current_line_points.append(point)
                            st.rerun()
        else:
            st.info("Créez d'abord des points dans l'onglet Points")
    
    with col2:
        st.subheader("Ligne courante")
        
        line_name = st.text_input("Nom de la ligne")
        
        col_style1, col_style2 = st.columns(2)
        with col_style1:
            line_color = st.selectbox("Couleur", 
                                    ["rouge", "vert", "bleu", "jaune", "orange", "cyan", "magenta", "noir", "blanc"], key="line_color")
        with col_style2:
            line_width = st.number_input("Épaisseur", value=5, min_value=1, max_value=20, key="line_width")
        
        # Affichage des points de la ligne
        if st.session_state.current_line_points:
            st.write("**Points de la ligne (dans l'ordre) :**")
            for i, point in enumerate(st.session_state.current_line_points):
                col_order, col_point, col_actions = st.columns([0.5, 2.5, 1])
                with col_order:
                    st.write(f"**{i+1}.**")
                with col_point:
                    st.write(f"{point['name']} ({point['lat']:.4f}, {point['lon']:.4f})")
                with col_actions:
                    col_up, col_down, col_del = st.columns(3)
                    with col_up:
                        if i > 0 and st.button("⬆️", key=f"up_line_{i}"):
                            st.session_state.current_line_points[i], st.session_state.current_line_points[i-1] = st.session_state.current_line_points[i-1], st.session_state.current_line_points[i]
                            st.rerun()
                    with col_down:
                        if i < len(st.session_state.current_line_points)-1 and st.button("⬇️", key=f"down_line_{i}"):
                            st.session_state.current_line_points[i], st.session_state.current_line_points[i+1] = st.session_state.current_line_points[i+1], st.session_state.current_line_points[i]
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"remove_line_point_{i}"):
                            st.session_state.current_line_points.pop(i)
                            st.rerun()
        
        col_validate, col_clear = st.columns(2)
        with col_validate:
            if len(st.session_state.current_line_points) >= 2 and line_name:
                if st.button("✅ Valider la ligne", use_container_width=True):
                    if not any(l['name'] == line_name for l in st.session_state.lines_data):
                        line_coords = [(p["lon"], p["lat"]) for p in st.session_state.current_line_points]
                        st.session_state.lines_data.append({
                            "type": "Ligne", "name": line_name, "points": line_coords,
                            "description": "", "color": line_color, "width": line_width
                        })
                        st.session_state.current_line_points = []
                        st.success(f"Ligne '{line_name}' créée!")
                        st.rerun()
                    else:
                        st.error("Nom de ligne déjà existant")
            elif not line_name:
                st.info("Saisissez un nom pour la ligne")
            else:
                st.info("Ajoutez au moins 2 points")
        
        with col_clear:
            if st.button("🔄 Vider la ligne", use_container_width=True):
                st.session_state.current_line_points = []
                st.rerun()
        

    
    # Liste des lignes existantes
    if st.session_state.lines_data:
        st.subheader("Lignes existantes")
        for i, line in enumerate(st.session_state.lines_data):
            with st.expander(f"📏 {line['name']}"):
                st.write(f"Points: {len(line['points'])}, Couleur: {line['color']}, Largeur: {line['width']}")
                if st.button(f"🗑️ Supprimer {line['name']}", key=f"del_line_list_{i}"):
                    st.session_state.lines_data.remove(line)
                    st.rerun()

# ONGLET CERCLES/ARCS
with tab4:
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Centre du cercle")
        
        # Choix du point existant
        if st.session_state.points_data:
            use_existing = st.checkbox("Utiliser un point existant")
            if use_existing:
                center_point_name = st.selectbox("Point centre", 
                                                [p['name'] for p in st.session_state.points_data], key="circle_center_point")
                center_point = next(p for p in st.session_state.points_data if p['name'] == center_point_name)
                center_lat, center_lon = center_point['lat'], center_point['lon']
            else:
                coord_format_circle = st.selectbox("Format coordonnées centre", 
                                                   ["Degrés décimaux", "Degrés Minutes", "Degrés Minutes Secondes", "Calamar"], key="circle_coord_format")
                
                if coord_format_circle == "Degrés décimaux":
                    center_lat_str = st.text_input("Latitude centre (ex: 44.5)")
                    center_lon_str = st.text_input("Longitude centre (ex: -1.65)")
                    if center_lat_str and center_lon_str:
                        try:
                            center_lat = float(center_lat_str)
                            center_lon = float(center_lon_str)
                        except ValueError:
                            st.error("Coordonnées invalides")
                            center_lat, center_lon = None, None
                    else:
                        center_lat, center_lon = None, None
                
                elif coord_format_circle == "Calamar":
                    col_x, col_y = st.columns(2)
                    with col_x:
                        x_val = st.number_input("Axe Y", value=0.0, key="circle_calamar_x")
                        x_unit = st.selectbox("Unité Y", ["mL", "mC"], key="circle_calamar_x_unit")
                    with col_y:
                        y_val = st.number_input("Axe X", value=0.0, key="circle_calamar_y")
                        y_unit = st.selectbox("Unité X", ["mD", "mG"], key="circle_calamar_y_unit")
                    
                    center_lat, center_lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
                    st.info(f"Coordonnées GPS: {center_lat:.6f}, {center_lon:.6f}")
                
                elif coord_format_circle == "Degrés Minutes":
                    col_lat_deg, col_lat_min, col_lat_dir = st.columns([2, 2, 1])
                    with col_lat_deg:
                        lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="circle_dm_lat_deg")
                    with col_lat_min:
                        lat_min = st.number_input("Lat '", value=31.2, min_value=0.0, max_value=59.999, format="%.3f", key="circle_dm_lat_min")
                    with col_lat_dir:
                        lat_dir = st.selectbox("N/S", ["N", "S"], key="circle_dm_lat_dir")
                    
                    col_lon_deg, col_lon_min, col_lon_dir = st.columns([2, 2, 1])
                    with col_lon_deg:
                        lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="circle_dm_lon_deg")
                    with col_lon_min:
                        lon_min = st.number_input("Lon '", value=7.2, min_value=0.0, max_value=59.999, format="%.3f", key="circle_dm_lon_min")
                    with col_lon_dir:
                        lon_dir = st.selectbox("E/W", ["E", "W"], key="circle_dm_lon_dir")
                    
                    center_lat = lat_deg + lat_min/60
                    center_lon = lon_deg + lon_min/60
                    if lat_dir == 'S': center_lat = -center_lat
                    if lon_dir == 'W': center_lon = -center_lon
                
                else:  # DMS
                    col_lat_deg, col_lat_min, col_lat_sec, col_lat_dir = st.columns([2, 2, 2, 1])
                    with col_lat_deg:
                        lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="circle_dms_lat_deg")
                    with col_lat_min:
                        lat_min = st.number_input("Lat '", value=31, min_value=0, max_value=59, key="circle_dms_lat_min")
                    with col_lat_sec:
                        lat_sec = st.number_input("Lat \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="circle_dms_lat_sec")
                    with col_lat_dir:
                        lat_dir = st.selectbox("N/S", ["N", "S"], key="circle_dms_lat_dir")
                    
                    col_lon_deg, col_lon_min, col_lon_sec, col_lon_dir = st.columns([2, 2, 2, 1])
                    with col_lon_deg:
                        lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="circle_dms_lon_deg")
                    with col_lon_min:
                        lon_min = st.number_input("Lon '", value=7, min_value=0, max_value=59, key="circle_dms_lon_min")
                    with col_lon_sec:
                        lon_sec = st.number_input("Lon \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="circle_dms_lon_sec")
                    with col_lon_dir:
                        lon_dir = st.selectbox("E/W", ["E", "W"], key="circle_dms_lon_dir")
                    
                    center_lat = lat_deg + lat_min/60 + lat_sec/3600
                    center_lon = lon_deg + lon_min/60 + lon_sec/3600
                    if lat_dir == 'S': center_lat = -center_lat
                    if lon_dir == 'W': center_lon = -center_lon
        else:
            coord_format_circle = st.selectbox("Format coordonnées centre", 
                                               ["Degrés décimaux", "Degrés Minutes", "Degrés Minutes Secondes", "Calamar"], key="circle_coord_format_no_points")
            
            if coord_format_circle == "Degrés décimaux":
                center_lat_str = st.text_input("Latitude centre (ex: 44.5)")
                center_lon_str = st.text_input("Longitude centre (ex: -1.65)")
                if center_lat_str and center_lon_str:
                    try:
                        center_lat = float(center_lat_str)
                        center_lon = float(center_lon_str)
                    except ValueError:
                        st.error("Coordonnées invalides")
                        center_lat, center_lon = None, None
                else:
                    center_lat, center_lon = None, None
            
            elif coord_format_circle == "Calamar":
                col_x, col_y = st.columns(2)
                with col_x:
                    x_val = st.number_input("Axe Y", value=0.0, key="circle_calamar_x_no_points")
                    x_unit = st.selectbox("Unité Y", ["mL", "mC"], key="circle_calamar_x_unit_no_points")
                with col_y:
                    y_val = st.number_input("Axe X", value=0.0, key="circle_calamar_y_no_points")
                    y_unit = st.selectbox("Unité X", ["mD", "mG"], key="circle_calamar_y_unit_no_points")
                
                center_lat, center_lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
                st.info(f"Coordonnées GPS: {center_lat:.6f}, {center_lon:.6f}")
            
            elif coord_format_circle == "Degrés Minutes":
                col_lat_deg, col_lat_min, col_lat_dir = st.columns([2, 2, 1])
                with col_lat_deg:
                    lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="circle_dm_lat_deg_no_points")
                with col_lat_min:
                    lat_min = st.number_input("Lat '", value=31.2, min_value=0.0, max_value=59.999, format="%.3f", key="circle_dm_lat_min_no_points")
                with col_lat_dir:
                    lat_dir = st.selectbox("N/S", ["N", "S"], key="circle_dm_lat_dir_no_points")
                
                col_lon_deg, col_lon_min, col_lon_dir = st.columns([2, 2, 1])
                with col_lon_deg:
                    lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="circle_dm_lon_deg_no_points")
                with col_lon_min:
                    lon_min = st.number_input("Lon '", value=7.2, min_value=0.0, max_value=59.999, format="%.3f", key="circle_dm_lon_min_no_points")
                with col_lon_dir:
                    lon_dir = st.selectbox("E/W", ["E", "W"], key="circle_dm_lon_dir_no_points")
                
                center_lat = lat_deg + lat_min/60
                center_lon = lon_deg + lon_min/60
                if lat_dir == 'S': center_lat = -center_lat
                if lon_dir == 'W': center_lon = -center_lon
            
            else:  # DMS
                col_lat_deg, col_lat_min, col_lat_sec, col_lat_dir = st.columns([2, 2, 2, 1])
                with col_lat_deg:
                    lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="circle_dms_lat_deg_no_points")
                with col_lat_min:
                    lat_min = st.number_input("Lat '", value=31, min_value=0, max_value=59, key="circle_dms_lat_min_no_points")
                with col_lat_sec:
                    lat_sec = st.number_input("Lat \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="circle_dms_lat_sec_no_points")
                with col_lat_dir:
                    lat_dir = st.selectbox("N/S", ["N", "S"], key="circle_dms_lat_dir_no_points")
                
                col_lon_deg, col_lon_min, col_lon_sec, col_lon_dir = st.columns([2, 2, 2, 1])
                with col_lon_deg:
                    lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="circle_dms_lon_deg_no_points")
                with col_lon_min:
                    lon_min = st.number_input("Lon '", value=7, min_value=0, max_value=59, key="circle_dms_lon_min_no_points")
                with col_lon_sec:
                    lon_sec = st.number_input("Lon \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="circle_dms_lon_sec_no_points")
                with col_lon_dir:
                    lon_dir = st.selectbox("E/W", ["E", "W"], key="circle_dms_lon_dir_no_points")
                
                center_lat = lat_deg + lat_min/60 + lat_sec/3600
                center_lon = lon_deg + lon_min/60 + lon_sec/3600
                if lat_dir == 'S': center_lat = -center_lat
                if lon_dir == 'W': center_lon = -center_lon
    
    with col2:
        st.subheader("Paramètres")
        
        circle_name = st.text_input("Nom du cercle/arc")
        
        col_radius, col_segments = st.columns(2)
        with col_radius:
            radius_val = st.number_input("Rayon", value=1.0, min_value=0.1, key="circle_radius")
            radius_unit = st.selectbox("Unité rayon", ["nautiques", "mètres"], key="circle_radius_unit")
        with col_segments:
            num_segments = st.number_input("Segments", value=72, min_value=8, max_value=360, key="circle_segments")
        
        is_arc = st.checkbox("Créer un arc de cercle")
        
        if is_arc:
            col_start, col_end = st.columns(2)
            with col_start:
                start_angle = st.number_input("Angle début (°)", value=0.0, min_value=0.0, max_value=360.0, key="circle_start_angle")
            with col_end:
                end_angle = st.number_input("Angle fin (°)", value=90.0, min_value=0.0, max_value=360.0, key="circle_end_angle")
            
            close_arc = st.checkbox("Fermer l'arc (relier au centre)", value=True)
        else:
            start_angle, end_angle = 0, 360
            close_arc = False
        
        col_color, col_width = st.columns(2)
        with col_color:
            circle_color = st.selectbox("Couleur", 
                                      ["rouge", "vert", "bleu", "jaune", "orange", "cyan", "magenta", "noir", "blanc"], key="circle_color")
        with col_width:
            circle_width = st.number_input("Épaisseur", value=5, min_value=1, max_value=20, key="circle_width")
        
        fill_circle = st.checkbox("Remplir le cercle/arc")
        
        if st.button("⭕ Générer Cercle/Arc", use_container_width=True):
            if circle_name:
                radius_km = radius_val * 1.852 if radius_unit == "nautiques" else radius_val / 1000
                close_arc_param = close_arc if is_arc else True
                circle_points = calculate_circle_points(center_lat, center_lon, radius_km, num_segments, is_arc, start_angle, end_angle, close_arc_param)
                
                circle_type = "Arc" if is_arc else "Cercle"
                circle_data = {
                    "type": circle_type, "name": circle_name, "center_lat": center_lat, "center_lon": center_lon,
                    "radius_km": radius_km, "radius_unit": radius_unit, "num_segments": num_segments, 
                    "points": circle_points, "color": circle_color, "width": circle_width, "fill": fill_circle
                }
                
                if is_arc:
                    circle_data["start_angle"] = start_angle
                    circle_data["end_angle"] = end_angle
                    circle_data["close_arc"] = close_arc_param
                
                st.session_state.circles_data.append(circle_data)
                st.success(f"{circle_type} '{circle_name}' généré!")
                st.rerun()
            else:
                st.error("Nom requis")
    
    # Liste des cercles existants
    if st.session_state.circles_data:
        st.subheader("Cercles/Arcs existants")
        for i, circle in enumerate(st.session_state.circles_data):
            with st.expander(f"⭕ {circle['name']}"):
                radius_display = circle['radius_km'] / 1.852 if circle['radius_unit'] == 'nautiques' else circle['radius_km'] * 1000
                unit_display = "NM" if circle['radius_unit'] == 'nautiques' else "m"
                st.write(f"Centre: ({circle['center_lat']:.4f}, {circle['center_lon']:.4f})")
                st.write(f"Rayon: {radius_display:.2f}{unit_display}, Couleur: {circle['color']}")
                if st.button(f"🗑️ Supprimer {circle['name']}", key=f"del_circle_list_{i}"):
                    st.session_state.circles_data.remove(circle)
                    st.rerun()

# ONGLET POLYGONES
with tab5:
    
    tab1, tab2 = st.tabs(["Polygone libre", "Rectangle orienté"])
    
    with tab1:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Points disponibles")
            if st.session_state.points_data:
                st.write("Cliquez sur un point pour l'ajouter au polygone :")
                for i, point in enumerate(st.session_state.points_data):
                    col_point, col_add = st.columns([3, 1])
                    with col_point:
                        st.write(f"**{point['name']}** - {point['lat']:.4f}, {point['lon']:.4f}")
                    with col_add:
                        if st.button("➕", key=f"add_poly_{i}_{point['name']}"):
                            if point not in st.session_state.current_polygon_points:
                                st.session_state.current_polygon_points.append(point)
                                st.rerun()
            else:
                st.info("Créez d'abord des points")
        
        with col2:
            st.subheader("Polygone courant")
            
            polygon_name = st.text_input("Nom du polygone")
            
            col_style1, col_style2 = st.columns(2)
            with col_style1:
                polygon_color = st.selectbox("Couleur", 
                                           ["rouge", "vert", "bleu", "jaune", "orange", "cyan", "magenta", "noir", "blanc"], key="polygon_color")
            with col_style2:
                polygon_width = st.number_input("Épaisseur", value=5, min_value=1, max_value=20, key="polygon_width")
            
            fill_polygon = st.checkbox("Remplir le polygone")
            
            # Affichage des points du polygone
            if st.session_state.current_polygon_points:
                st.write("**Points du polygone (dans l'ordre) :**")
                for i, point in enumerate(st.session_state.current_polygon_points):
                    col_order, col_point, col_actions = st.columns([0.5, 2.5, 1])
                    with col_order:
                        st.write(f"**{i+1}.**")
                    with col_point:
                        st.write(f"{point['name']} ({point['lat']:.4f}, {point['lon']:.4f})")
                    with col_actions:
                        col_up, col_down, col_del = st.columns(3)
                        with col_up:
                            if i > 0 and st.button("⬆️", key=f"up_poly_{i}"):
                                st.session_state.current_polygon_points[i], st.session_state.current_polygon_points[i-1] = st.session_state.current_polygon_points[i-1], st.session_state.current_polygon_points[i]
                                st.rerun()
                        with col_down:
                            if i < len(st.session_state.current_polygon_points)-1 and st.button("⬇️", key=f"down_poly_{i}"):
                                st.session_state.current_polygon_points[i], st.session_state.current_polygon_points[i+1] = st.session_state.current_polygon_points[i+1], st.session_state.current_polygon_points[i]
                                st.rerun()
                        with col_del:
                            if st.button("🗑️", key=f"remove_poly_point_{i}"):
                                st.session_state.current_polygon_points.pop(i)
                                st.rerun()
            
            if len(st.session_state.current_polygon_points) >= 3 and polygon_name:
                if st.button("✅ Valider le polygone", use_container_width=True):
                    polygon_coords = [(p["lon"], p["lat"]) for p in st.session_state.current_polygon_points]
                    polygon_coords.append(polygon_coords[0])  # Fermer le polygone
                    
                    st.session_state.rectangles_data.append({
                        "type": "Polygone", "name": polygon_name, "points": polygon_coords,
                        "description": "", "color": polygon_color, "width": polygon_width, "fill": fill_polygon
                    })
                    st.session_state.current_polygon_points = []
                    st.success(f"Polygone '{polygon_name}' créé!")
                    st.rerun()
            
            if st.button("🔄 Vider le polygone", use_container_width=True):
                st.session_state.current_polygon_points = []
                st.rerun()
    
    with tab2:
        st.subheader("Rectangle orienté")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            # Centre du rectangle
            if st.session_state.points_data:
                use_existing_rect = st.checkbox("Utiliser un point existant", key="rect_existing")
                if use_existing_rect:
                    rect_center_name = st.selectbox("Point centre", 
                                                   [p['name'] for p in st.session_state.points_data], key="rect_center")
                    rect_center = next(p for p in st.session_state.points_data if p['name'] == rect_center_name)
                    rect_center_lat, rect_center_lon = rect_center['lat'], rect_center['lon']
                else:
                    coord_format_rect = st.selectbox("Format coordonnées centre", 
                                                     ["Degrés décimaux", "Degrés Minutes", "Degrés Minutes Secondes", "Calamar"], key="rect_coord_format")
                    
                    if coord_format_rect == "Degrés décimaux":
                        rect_center_lat_str = st.text_input("Latitude centre (ex: 44.5)", key="rect_lat")
                        rect_center_lon_str = st.text_input("Longitude centre (ex: -1.65)", key="rect_lon")
                        if rect_center_lat_str and rect_center_lon_str:
                            try:
                                rect_center_lat = float(rect_center_lat_str)
                                rect_center_lon = float(rect_center_lon_str)
                            except ValueError:
                                st.error("Coordonnées invalides")
                                rect_center_lat, rect_center_lon = None, None
                        else:
                            rect_center_lat, rect_center_lon = None, None
                    
                    elif coord_format_rect == "Calamar":
                        col_x, col_y = st.columns(2)
                        with col_x:
                            x_val = st.number_input("Axe Y", value=0.0, key="rect_calamar_x")
                            x_unit = st.selectbox("Unité Y", ["mL", "mC"], key="rect_calamar_x_unit")
                        with col_y:
                            y_val = st.number_input("Axe X", value=0.0, key="rect_calamar_y")
                            y_unit = st.selectbox("Unité X", ["mD", "mG"], key="rect_calamar_y_unit")
                        
                        rect_center_lat, rect_center_lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
                        st.info(f"Coordonnées GPS: {rect_center_lat:.6f}, {rect_center_lon:.6f}")
                    
                    elif coord_format_rect == "Degrés Minutes":
                        col_lat_deg, col_lat_min, col_lat_dir = st.columns([2, 2, 1])
                        with col_lat_deg:
                            lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="rect_dm_lat_deg")
                        with col_lat_min:
                            lat_min = st.number_input("Lat '", value=31.2, min_value=0.0, max_value=59.999, format="%.3f", key="rect_dm_lat_min")
                        with col_lat_dir:
                            lat_dir = st.selectbox("N/S", ["N", "S"], key="rect_dm_lat_dir")
                        
                        col_lon_deg, col_lon_min, col_lon_dir = st.columns([2, 2, 1])
                        with col_lon_deg:
                            lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="rect_dm_lon_deg")
                        with col_lon_min:
                            lon_min = st.number_input("Lon '", value=7.2, min_value=0.0, max_value=59.999, format="%.3f", key="rect_dm_lon_min")
                        with col_lon_dir:
                            lon_dir = st.selectbox("E/W", ["E", "W"], key="rect_dm_lon_dir")
                        
                        rect_center_lat = lat_deg + lat_min/60
                        rect_center_lon = lon_deg + lon_min/60
                        if lat_dir == 'S': rect_center_lat = -rect_center_lat
                        if lon_dir == 'W': rect_center_lon = -rect_center_lon
                    
                    else:  # DMS
                        col_lat_deg, col_lat_min, col_lat_sec, col_lat_dir = st.columns([2, 2, 2, 1])
                        with col_lat_deg:
                            lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="rect_dms_lat_deg")
                        with col_lat_min:
                            lat_min = st.number_input("Lat '", value=31, min_value=0, max_value=59, key="rect_dms_lat_min")
                        with col_lat_sec:
                            lat_sec = st.number_input("Lat \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="rect_dms_lat_sec")
                        with col_lat_dir:
                            lat_dir = st.selectbox("N/S", ["N", "S"], key="rect_dms_lat_dir")
                        
                        col_lon_deg, col_lon_min, col_lon_sec, col_lon_dir = st.columns([2, 2, 2, 1])
                        with col_lon_deg:
                            lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="rect_dms_lon_deg")
                        with col_lon_min:
                            lon_min = st.number_input("Lon '", value=7, min_value=0, max_value=59, key="rect_dms_lon_min")
                        with col_lon_sec:
                            lon_sec = st.number_input("Lon \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="rect_dms_lon_sec")
                        with col_lon_dir:
                            lon_dir = st.selectbox("E/W", ["E", "W"], key="rect_dms_lon_dir")
                        
                        rect_center_lat = lat_deg + lat_min/60 + lat_sec/3600
                        rect_center_lon = lon_deg + lon_min/60 + lon_sec/3600
                        if lat_dir == 'S': rect_center_lat = -rect_center_lat
                        if lon_dir == 'W': rect_center_lon = -rect_center_lon
            else:
                coord_format_rect = st.selectbox("Format coordonnées centre", 
                                                 ["Degrés décimaux", "Degrés Minutes", "Degrés Minutes Secondes", "Calamar"], key="rect_coord_format_no_points")
                
                if coord_format_rect == "Degrés décimaux":
                    rect_center_lat_str = st.text_input("Latitude centre (ex: 44.5)", key="rect_lat_2")
                    rect_center_lon_str = st.text_input("Longitude centre (ex: -1.65)", key="rect_lon_2")
                    if rect_center_lat_str and rect_center_lon_str:
                        try:
                            rect_center_lat = float(rect_center_lat_str)
                            rect_center_lon = float(rect_center_lon_str)
                        except ValueError:
                            st.error("Coordonnées invalides")
                            rect_center_lat, rect_center_lon = None, None
                    else:
                        rect_center_lat, rect_center_lon = None, None
                
                elif coord_format_rect == "Calamar":
                    col_x, col_y = st.columns(2)
                    with col_x:
                        x_val = st.number_input("Axe Y", value=0.0, key="rect_calamar_x_no_points")
                        x_unit = st.selectbox("Unité Y", ["mL", "mC"], key="rect_calamar_x_unit_no_points")
                    with col_y:
                        y_val = st.number_input("Axe X", value=0.0, key="rect_calamar_y_no_points")
                        y_unit = st.selectbox("Unité X", ["mD", "mG"], key="rect_calamar_y_unit_no_points")
                    
                    rect_center_lat, rect_center_lon = convert_calamar_to_gps(x_val, y_val, x_unit, y_unit)
                    st.info(f"Coordonnées GPS: {rect_center_lat:.6f}, {rect_center_lon:.6f}")
                
                elif coord_format_rect == "Degrés Minutes":
                    col_lat_deg, col_lat_min, col_lat_dir = st.columns([2, 2, 1])
                    with col_lat_deg:
                        lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="rect_dm_lat_deg_no_points")
                    with col_lat_min:
                        lat_min = st.number_input("Lat '", value=31.2, min_value=0.0, max_value=59.999, format="%.3f", key="rect_dm_lat_min_no_points")
                    with col_lat_dir:
                        lat_dir = st.selectbox("N/S", ["N", "S"], key="rect_dm_lat_dir_no_points")
                    
                    col_lon_deg, col_lon_min, col_lon_dir = st.columns([2, 2, 1])
                    with col_lon_deg:
                        lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="rect_dm_lon_deg_no_points")
                    with col_lon_min:
                        lon_min = st.number_input("Lon '", value=7.2, min_value=0.0, max_value=59.999, format="%.3f", key="rect_dm_lon_min_no_points")
                    with col_lon_dir:
                        lon_dir = st.selectbox("E/W", ["E", "W"], key="rect_dm_lon_dir_no_points")
                    
                    rect_center_lat = lat_deg + lat_min/60
                    rect_center_lon = lon_deg + lon_min/60
                    if lat_dir == 'S': rect_center_lat = -rect_center_lat
                    if lon_dir == 'W': rect_center_lon = -rect_center_lon
                
                else:  # DMS
                    col_lat_deg, col_lat_min, col_lat_sec, col_lat_dir = st.columns([2, 2, 2, 1])
                    with col_lat_deg:
                        lat_deg = st.number_input("Lat °", value=44, min_value=0, max_value=90, key="rect_dms_lat_deg_no_points")
                    with col_lat_min:
                        lat_min = st.number_input("Lat '", value=31, min_value=0, max_value=59, key="rect_dms_lat_min_no_points")
                    with col_lat_sec:
                        lat_sec = st.number_input("Lat \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="rect_dms_lat_sec_no_points")
                    with col_lat_dir:
                        lat_dir = st.selectbox("N/S", ["N", "S"], key="rect_dms_lat_dir_no_points")
                    
                    col_lon_deg, col_lon_min, col_lon_sec, col_lon_dir = st.columns([2, 2, 2, 1])
                    with col_lon_deg:
                        lon_deg = st.number_input("Lon °", value=1, min_value=0, max_value=180, key="rect_dms_lon_deg_no_points")
                    with col_lon_min:
                        lon_min = st.number_input("Lon '", value=7, min_value=0, max_value=59, key="rect_dms_lon_min_no_points")
                    with col_lon_sec:
                        lon_sec = st.number_input("Lon \"", value=12.0, min_value=0.0, max_value=59.999, format="%.2f", key="rect_dms_lon_sec_no_points")
                    with col_lon_dir:
                        lon_dir = st.selectbox("E/W", ["E", "W"], key="rect_dms_lon_dir_no_points")
                    
                    rect_center_lat = lat_deg + lat_min/60 + lat_sec/3600
                    rect_center_lon = lon_deg + lon_min/60 + lon_sec/3600
                    if lat_dir == 'S': rect_center_lat = -rect_center_lat
                    if lon_dir == 'W': rect_center_lon = -rect_center_lon
        
        with col2:
            rect_name = st.text_input("Nom du rectangle")
            
            col_length, col_width_rect = st.columns(2)
            with col_length:
                length_val = st.number_input("Longueur", value=1.0, min_value=0.1, key="rect_length")
                length_unit = st.selectbox("Unité longueur", ["nautiques", "mètres"], key="rect_length_unit")
            with col_width_rect:
                width_val = st.number_input("Largeur", value=0.5, min_value=0.1, key="rect_width_val")
                width_unit = st.selectbox("Unité largeur", ["nautiques", "mètres"], key="rect_width_unit")
            
            bearing_deg = st.number_input("Cap (degrés)", value=0, min_value=0, max_value=359, key="rect_bearing")
            
            col_rect_color, col_rect_width = st.columns(2)
            with col_rect_color:
                rect_color = st.selectbox("Couleur", 
                                        ["rouge", "vert", "bleu", "jaune", "orange", "cyan", "magenta", "noir", "blanc"], key="rect_color")
            with col_rect_width:
                rect_width = st.number_input("Épaisseur", value=5, min_value=1, max_value=20, key="rect_width")
            
            fill_rect = st.checkbox("Remplir le rectangle")
            add_arrow = st.checkbox("Ajouter flèche d'orientation")
            
            if st.button("🔷 Générer Rectangle", use_container_width=True):
                if rect_name:
                    length_km = length_val * 1.852 if length_unit == "nautiques" else length_val / 1000
                    width_km = width_val * 1.852 if width_unit == "nautiques" else width_val / 1000
                    
                    rectangle_points = calculate_rectangle_points(rect_center_lat, rect_center_lon, length_km, width_km, bearing_deg)
                    
                    rect_data = {
                        "type": "Rectangle", "name": rect_name, "center_lat": rect_center_lat, "center_lon": rect_center_lon,
                        "length_km": length_km, "width_km": width_km, "bearing_deg": bearing_deg,
                        "length_unit": length_unit, "width_unit": width_unit,
                        "points": rectangle_points, "color": rect_color, "width": rect_width,
                        "fill": fill_rect, "add_arrow": add_arrow
                    }
                    
                    st.session_state.rectangles_data.append(rect_data)
                    st.success(f"Rectangle '{rect_name}' généré!")
                    st.rerun()
                else:
                    st.error("Nom requis")
    
    # Liste des polygones/rectangles existants
    if st.session_state.rectangles_data:
        st.subheader("Polygones/Rectangles existants")
        for i, rect in enumerate(st.session_state.rectangles_data):
            with st.expander(f"🔷 {rect['name']}"):
                if 'length_km' in rect:
                    st.write(f"Rectangle - Centre: ({rect['center_lat']:.4f}, {rect['center_lon']:.4f})")
                    st.write(f"Dimensions: {rect['length_km']*1000:.0f}m x {rect['width_km']*1000:.0f}m")
                else:
                    st.write(f"Polygone - {len(rect['points'])} points")
                if st.button(f"🗑️ Supprimer {rect['name']}", key=f"del_rect_list_{i}"):
                    st.session_state.rectangles_data.remove(rect)
                    st.rerun()

# ONGLET DIVERS
with tab6:
    st.subheader("🔧 Outils de diagnostic")
    
    # Test de l'API
    if st.button("🔍 Tester l'API MBTiles"):
        if not is_api_configured():
            st.error("API non configurée")
        else:
            try:
                response = requests.get(f"{get_api_url()}/health", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('tippecanoe_available'):
                        st.success("✅ API opérationnelle avec Tippecanoe")
                    else:
                        st.warning("⚠️ API opérationnelle mais Tippecanoe indisponible")
                else:
                    st.error(f"❌ API inaccessible (status: {response.status_code})")
            except Exception as e:
                st.error(f"❌ Erreur de connexion API: {e}")
    
    # Test de conversion simple
    if st.button("🧪 Test conversion MBTiles simple"):
        if not is_api_configured():
            st.error("API non configurée")
        else:
            # Créer un KML de test simple
            test_kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Point</name>
      <Point>
        <coordinates>-1.12,44.52,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Test Line</name>
      <LineString>
        <coordinates>-1.12,44.52,0 -1.11,44.53,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Test Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>-1.12,44.52,0 -1.11,44.52,0 -1.11,44.53,0 -1.12,44.53,0 -1.12,44.52,0</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>'''
            
            try:
                mbtiles_data = convert_kml_to_mbtiles(test_kml, name="test_simple")
                st.success(f"✅ Conversion MBTiles réussie! Taille: {len(mbtiles_data)} bytes")
                st.download_button(
                    label="💾 Télécharger test MBTiles",
                    data=mbtiles_data,
                    file_name="test_simple.mbtiles",
                    mime="application/octet-stream"
                )
            except Exception as e:
                st.error(f"❌ Échec conversion: {e}")
    
    st.markdown("---")
    st.subheader("Calculer distance et gisement")
    
    if len(st.session_state.points_data) >= 2:
        col1, col2 = st.columns(2)
        with col1:
            point_a = st.selectbox("Point A", [p['name'] for p in st.session_state.points_data], key="calc_point_a")
        with col2:
            point_b = st.selectbox("Point B", [p['name'] for p in st.session_state.points_data], key="calc_point_b")
        
        if st.button("📐 Calculer") and point_a != point_b:
            p_a = next(p for p in st.session_state.points_data if p['name'] == point_a)
            p_b = next(p for p in st.session_state.points_data if p['name'] == point_b)
            
            distance_m = calculate_distance(p_a['lat'], p_a['lon'], p_b['lat'], p_b['lon'])
            distance_km = distance_m / 1000
            distance_nm = distance_km / 1.852
            bearing = calculate_bearing(p_a['lat'], p_a['lon'], p_b['lat'], p_b['lon'])
            
            st.success(f"Distance: {distance_km:.2f}km ({distance_nm:.2f}NM) - Gisement: {bearing:.1f}°")
    else:
        st.info("Créez au moins 2 points pour utiliser cette fonction")

# ONGLET VISUALISATION
with tab7:
    

    

    # Contrôle des données de référence
    col_ref1, col_ref2 = st.columns([3, 1])
    with col_ref1:
        show_ref = st.checkbox("📍 Afficher données de référence SDVFR", value=st.session_state.show_reference)
        if show_ref != st.session_state.show_reference:
            st.session_state.show_reference = show_ref
            st.rerun()
    
    with col_ref2:
        if st.button("🔄 Recharger référence"):
            if load_reference_kml():
                st.success("Référence rechargée!")
                st.rerun()
            else:
                st.info("Aucun fichier reference.kml trouvé")
    
    # Charger les données de référence au premier lancement
    if not any(st.session_state.reference_data.values()):
        load_reference_kml()
    
    # Message informatif
    st.info("💡 **Astuce :** Cliquez directement sur la carte pour créer un point à l'endroit souhaité !")
    
    # Créer et afficher la carte
    m = create_map()
    
    # Afficher la carte
    map_data = st_folium(m, use_container_width=True, height=500, returned_objects=["last_clicked"])
    
    # Gestion du clic sur la carte
    if map_data['last_clicked'] is not None:
        clicked_lat = map_data['last_clicked']['lat']
        clicked_lon = map_data['last_clicked']['lng']
        
        # Vérifier si c'est un nouveau clic
        if 'clicked_position' not in st.session_state or st.session_state.clicked_position != [clicked_lat, clicked_lon]:
            # Sauvegarder la position cliquée dans la session
            st.session_state.clicked_position = [clicked_lat, clicked_lon]
            # Forcer la mise à jour pour afficher le marqueur
            st.rerun()
    
    # Afficher le formulaire si une position est sélectionnée
    if st.session_state.clicked_position is not None:
        clicked_lat, clicked_lon = st.session_state.clicked_position
        
        # Encart visible pour la création de point
        st.markdown("---")
        st.success(f"🎯 **Position sélectionnée :** {clicked_lat:.6f}, {clicked_lon:.6f}")
        
        # Formulaire pour créer un point depuis le clic
        st.subheader("📍 Créer un point à cette position")
        point_name_click = st.text_input("Nom du point à créer", placeholder="Entrez le nom du point...", key="point_name_from_click")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("➕ Créer point depuis clic", use_container_width=True, key="create_point_btn"):
                if point_name_click and not any(p['name'] == point_name_click for p in st.session_state.points_data):
                    st.session_state.points_data.append({
                        "type": "Point", "name": point_name_click, 
                        "lat": clicked_lat, "lon": clicked_lon, 
                        "description": "Créé depuis la carte"
                    })
                    # Effacer la position cliquée après création du point
                    st.session_state.clicked_position = None
                    st.success(f"Point '{point_name_click}' créé!")
                    st.rerun()
                elif not point_name_click:
                    st.error("Veuillez saisir un nom pour le point")
                else:
                    st.error("Ce nom de point existe déjà")
        
        with col2:
            if st.button("❌ Annuler", use_container_width=True, key="cancel_point_btn"):
                st.session_state.clicked_position = None
                st.rerun()
        
        st.markdown("---")
    
    # Gestion des objets KML
    if any([st.session_state.points_data, st.session_state.lines_data, st.session_state.circles_data, st.session_state.rectangles_data]):
        st.markdown("---")
        st.subheader("🛠️ Gestion des objets KML")
        
        # Points
        if st.session_state.points_data:
            st.write(f"**📍 Points ({len(st.session_state.points_data)})**")
            for i, point in enumerate(st.session_state.points_data):
                col_info, col_action = st.columns([4, 1])
                with col_info:
                    st.write(f"**{point['name']}**: {point['lat']:.4f}, {point['lon']:.4f}")
                with col_action:
                    if st.button("🗑️", key=f"del_point_viz_{i}"):
                        st.session_state.points_data.remove(point)
                        st.rerun()
        
        # Lignes
        if st.session_state.lines_data:
            st.write(f"**📏 Lignes ({len(st.session_state.lines_data)})**")
            for i, line in enumerate(st.session_state.lines_data):
                col_info, col_action = st.columns([4, 1])
                with col_info:
                    st.write(f"**{line['name']}**: {len(line['points'])} points, {line['color']}")
                with col_action:
                    if st.button("🗑️", key=f"del_line_viz_{i}"):
                        st.session_state.lines_data.remove(line)
                        st.rerun()
        
        # Cercles
        if st.session_state.circles_data:
            st.write(f"**⭕ Cercles/Arcs ({len(st.session_state.circles_data)})**")
            for i, circle in enumerate(st.session_state.circles_data):
                radius_display = circle['radius_km'] / 1.852 if circle['radius_unit'] == 'nautiques' else circle['radius_km'] * 1000
                unit_display = "NM" if circle['radius_unit'] == 'nautiques' else "m"
                
                col_info, col_action = st.columns([4, 1])
                with col_info:
                    st.write(f"**{circle['name']}**: R={radius_display:.2f}{unit_display}, {circle['color']}")
                with col_action:
                    if st.button("🗑️", key=f"del_circle_viz_{i}"):
                        st.session_state.circles_data.remove(circle)
                        st.rerun()
        
        # Rectangles/Polygones
        if st.session_state.rectangles_data:
            st.write(f"**🔷 Polygones/Rectangles ({len(st.session_state.rectangles_data)})**")
            for i, rect in enumerate(st.session_state.rectangles_data):
                col_info, col_action = st.columns([4, 1])
                with col_info:
                    if 'length_km' in rect:
                        st.write(f"**{rect['name']}** (Rectangle): {rect['length_km']*1000:.0f}m x {rect['width_km']*1000:.0f}m")
                    else:
                        st.write(f"**{rect['name']}** (Polygone): {len(rect['points'])} points")
                with col_action:
                    if st.button("🗑️", key=f"del_rect_viz_{i}"):
                        st.session_state.rectangles_data.remove(rect)
                        st.rerun()
    else:
        st.markdown("---")
        st.info("💡 Aucun objet KML présent. Créez des objets dans les autres onglets ou importez un fichier KML.")
    
    # Section pour charger des cartes personnalisées
    st.markdown("---")
    st.subheader("🗺️ Charger une carte personnalisée")
    
    uploaded_map = st.file_uploader(
        "Fichier TIFF géoréférencé ou MBTiles", 
        type=['tiff', 'tif', 'mbtiles'],
        key="custom_map_uploader"
    )
    
    if uploaded_map is not None:
        file_extension = uploaded_map.name.split('.')[-1].lower()
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**Fichier :** {uploaded_map.name}")
            st.write(f"**Type :** {file_extension.upper()}")
            st.write(f"**Taille :** {uploaded_map.size / 1024 / 1024:.1f} MB")
        
        with col2:
            if st.button("📥 Charger", key="load_custom_map"):
                if file_extension in ['tiff', 'tif'] and not RASTERIO_AVAILABLE:
                    st.error("📦 Installation requise: pip install rasterio pillow")
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp_file:
                        tmp_file.write(uploaded_map.read())
                        tmp_path = tmp_file.name
                    
                    valid_file = True
                    if file_extension in ['tiff', 'tif'] and RASTERIO_AVAILABLE:
                        try:
                            with rasterio.open(tmp_path) as src:
                                if src.crs is None:
                                    st.error("❌ Fichier TIFF non géoréférencé")
                                    os.unlink(tmp_path)
                                    valid_file = False
                                else:
                                    st.success(f"✅ TIFF géoréférencé détecté (CRS: {src.crs})")
                        except Exception as e:
                            st.error(f"❌ Erreur lecture TIFF: {e}")
                            os.unlink(tmp_path)
                            valid_file = False
                    
                    if valid_file:
                        tile_info = {
                            'name': uploaded_map.name.split('.')[0],
                            'type': 'mbtiles' if file_extension == 'mbtiles' else 'tiff',
                            'path': tmp_path,
                            'size': uploaded_map.size
                        }
                        
                        st.session_state.custom_tiles.append(tile_info)
                        st.success(f"Carte '{uploaded_map.name}' chargée!")
                        st.rerun()
    
    # Afficher les cartes chargées
    if st.session_state.custom_tiles:
        st.write("**Cartes chargées :**")
        for i, tile in enumerate(st.session_state.custom_tiles):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.caption(f"📄 {tile['name']} ({tile['type'].upper()})")
            with col2:
                st.caption(f"{tile['size'] / 1024 / 1024:.1f} MB")
            with col3:
                if st.button("🗑️", key=f"del_tile_{i}"):
                    try:
                        os.unlink(tile['path'])
                    except:
                        pass
                    st.session_state.custom_tiles.pop(i)
                    st.rerun()


# Footer
st.markdown("---")
st.markdown("*Générateur KML pour SDVFR - Version Streamlit par Valentin BALAYN*")