# KML Generator - Générateur KML pour SDVFR

Application web Streamlit pour générer des fichiers KML destinés à la navigation aérienne.

## 🚀 Installation rapide

### Prérequis
- Python 3.8 ou supérieur

### Installation automatique (Windows)
```bash
# Cloner le repository
git clone https://github.com/[votre-username]/kml-generator.git
cd kml-generator

# Lancer l'installation et l'application
run.bat
```

### Installation manuelle
```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
streamlit run streamlit_app.py
```

L'application s'ouvrira automatiquement dans votre navigateur à l'adresse `http://localhost:8501`

## ✨ Fonctionnalités

### 📍 Points
- Création de points individuels (coordonnées décimales, DMS, Calamar)
- Génération de points par relèvement/distance
- Conversion automatique des formats de coordonnées

### 📏 Lignes
- Création de lignes en reliant des points existants
- Personnalisation couleur et épaisseur
- Gestion de l'ordre des points

### ⭕ Cercles/Arcs
- Génération de cercles complets ou d'arcs
- Rayon en mètres ou nautiques
- Options de remplissage et style

### 🔷 Polygones
- Polygones libres à partir de points
- Rectangles orientés avec dimensions précises
- Flèches d'orientation optionnelles

### 🔧 Outils Divers
- Calcul distance/gisement entre points
- Conversions GPS (DMS ↔ Décimal)
- Système de coordonnées Calamar

### 🗺️ Visualisation
- Carte interactive avec tous les objets
- Création de points par clic sur carte
- Gestion complète des objets créés
- Support des cartes personnalisées (TIFF/MBTiles)

## 📱 Compatibilité

- ✅ Desktop (Windows, Mac, Linux)
- ✅ Mobile (iOS, Android)
- ✅ Tous navigateurs modernes

## 🎯 Export KML

Utilisez le bouton "Générer et télécharger KML" pour exporter tous vos objets au format KML compatible avec :
- Google Earth
- Logiciels de navigation aérienne
- Applications GPS

## 🛠️ Technologies

- **Streamlit** - Interface web
- **Folium** - Cartes interactives
- **SimpleKML** - Génération KML
- **Vincenty** - Calculs géodésiques haute précision

## 👨‍💻 Développement

Application développée par **Valentin BALAYN** pour la communauté **SDVFR**.

## 📄 License

MIT License - Voir le fichier LICENSE pour plus de détails.

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
- Signaler des bugs
- Proposer des améliorations
- Soumettre des pull requests

## 📞 Support

Pour toute question ou support, ouvrez une issue sur GitHub.