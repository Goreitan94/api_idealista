import os
import re
import requests
import pandas as pd
import numpy as np
import geopandas as gpd
import unicodedata
import json
from datetime import datetime
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
import folium

# ==============================
# Config
# ==============================
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

BASE_FOLDER = "/Idealista API (Datos)/Datos"
TEMPLATE = "plotly_dark"
PALETTE = px.colors.qualitative.Plotly

# ==============================
# OneDrive Helpers
# ==============================
def get_onedrive_token():
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {{"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "scope": "https://graph.microsoft.com/.default"}}
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    token_data = resp.json()
    if "access_token" in token_data:
        return token_data["access_token"]
    else:
        raise RuntimeError(f"No se pudo obtener token: {token_data}")

def list_folders(path, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{path}:/children"
    headers = {{"Authorization": f"Bearer {access_token}"}}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json().get("value", [])

def download_excel(path, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{path}:/content"
    headers = {{"Authorization": f"Bearer {access_token}"}}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return pd.read_excel(BytesIO(resp.content))

# ==============================
# Utils
# ==============================
def es_fecha(nombre: str) -> bool:
    try:
        datetime.strptime(nombre, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'ñ', 'n', text)
    text = re.sub(r'[\s\W]+', '-', text).strip('-')
    return text

def fmt_eur(x):
    try:
        return f"€{{x:,.0f}}".replace(",", ".")
    except:
        return ""

def fig_html(fig) -> str:
    """Convierte un objeto Plotly a HTML embebido."""
    return fig.to_html(full_html=False, include_plotlyjs=True,
                       config={{"displaylogo": False,
                               "modeBarButtonsToRemove": ["select", "lasso2d", "hovercompare"],
                               "scrollZoom": True, "responsive": True}})

# ==============================
# Mapas con Folium
# ==============================
def generar_mapa_barrio_folium(barrio_nombre, geojson_gdf, df_barrio):
    barrio_slug = slugify(barrio_nombre)
    barrio_gdf = geojson_gdf[geojson_gdf['slug'] == barrio_slug].to_crs(epsg=4326)

    # Centro
    if not barrio_gdf.empty:
        centroid = barrio_gdf.geometry.iloc[0].centroid
        center = (centroid.y, centroid.x)
    elif not df_barrio.empty:
        center = (df_barrio['latitude'].mean(), df_barrio['longitude'].mean())
    else:
        center = (40.4168, -3.7038)  # Madrid por defecto

    m = folium.Map(location=center, zoom_start=13, tiles='CartoDB positron')

    # Polígono del barrio
    if not barrio_gdf.empty:
        folium.GeoJson(
            barrio_gdf.geometry.iloc[0],
            style_function=lambda x: {{
                'color': 'white', 'weight': 2, 'fillColor': '#6c9ef8', 'fillOpacity': 0.5
            }}
        ).add_to(m)

    # Puntos de inmuebles
    if not df_barrio.empty and 'latitude' in df_barrio.columns and 'longitude' in df_barrio.columns:
        for _, row in df_barrio.iterrows():
            folium.CircleMarker(
                location=(row['latitude'], row['longitude']),
                radius=4,
                color='#ff7a59',
                fill=True,
                fill_opacity=0.8,
                popup=f"{fmt_eur(row['price'])} | {{int(row['size'])}} m²"
            ).add_to(m)

    return m._repr_html_()

# ==============================
# Gráficos Plotly
# ==============================
TEMPLATE = "plotly_dark"
PALETTE = px.colors.qualitative.Plotly

def histograma(df, col, title, color):
    if col not in df.columns or df[col].dropna().empty:
        return ""
    fig = px.histogram(df, x=col, nbins=30, template=TEMPLATE, title=title)
    fig.update_traces(marker_color=color, opacity=0.9, marker_line_color='rgb(255,255,255)', marker_line_width=0.5)
    return fig_html(fig)

def scatter_precio_size(df, color):
    if not set(["price", "size"]).issubset(df.columns) or df[["price","size"]].dropna().empty:
        return ""
    fig = px.scatter(df, x="size", y="price", template=TEMPLATE, title="Relación Precio vs Tamaño", hover_data=["rooms","price_per_m2"])
    fig.update_traces(marker=dict(size=8, line=dict(width=0.5, color="rgba(255,255,255,0.4)"), color=color), opacity=0.7)
    clean = df[["size","price"]].dropna()
    if len(clean) >= 2:
        m, b = np.polyfit(clean["size"], clean["price"], 1)
        x_line = np.linspace(clean["size"].min(), clean["size"].max(), 50)
        y_line = m * x_line + b
        fig.add_trace(go.Scatter(x=x_line, y=y_line, mode="lines", name="Tendencia", line=dict(width=2)))
    return fig_html(fig)

def tabla_html(df, title, sort_col, ascending, cols_order):
    usable = df.copy().sort_values(sort_col, ascending=ascending).head(10)
    usable = usable[[c for c in cols_order if c in usable.columns]]
    if usable.empty:
        return ""
    header_html = "".join([f"<th>{{c.replace('_', ' ').title().replace('Url', 'Anuncio')}}</th>" for c in usable.columns])
    rows_html = ""
    for _, row in usable.iterrows():
        cells_html = ""
        for c in usable.columns:
            val = row[c]
            if c == "price":
                val = fmt_eur(val)
            elif c == "price_per_m2":
                val = f"{{fmt_eur(val)}}/m²"
            elif c == "size":
                val = f"{{int(val):,}} m²".replace(",", ".")
            elif c == "url":
                val = f"<a href='{{val}}' target='_blank'>Ver Anuncio</a>"
            else:
                val = str(val)
            cells_html += f"<td>{{val}}</td>"
        rows_html += f"<tr>{{cells_html}}</tr>"
    html = f"""
    <div style="background:transparent; padding:0; margin-bottom:14px;">
        <h2 style="font-size:18px; text-align:center; margin:8px 6px 10px;">{{title}}</h2>
        <div style="max-height: 400px; overflow-y: auto;">
        <table style="width:100%; border-collapse:collapse; text-align:center;">
            <thead><tr style="background-color:#1a2445; color:white;">{{header_html}}</tr></thead>
            <tbody style="background-color:#121a33; color:white;">{{rows_html}}</tbody>
        </table></div></div>
    """
    return html

# ==============================
# Informe global
# ==============================
def generar_informe_global(all_dfs: list[pd.DataFrame], barrios: list[str], fecha: str, geojson_gdf):
    parts = [f"<html><head><meta charset='utf-8'><title>UrbenEye — {{fecha}}</title></head><body>"]
    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty: continue
        df_copy = df.copy()
        df_copy["barrio"] = slugify(barrio)
        df_all.append(df_copy)
    if not df_all:
        parts.append("<p>No hay datos.</p></body></html>")
        return "".join(parts)
    df_all = pd.concat(df_all, ignore_index=True)
    barrios_unicos = df_all['barrio'].unique().tolist()

    # Resumen general
    parts.append('<h2>Resumen general €/m² por barrio</h2>')
    m_ppm2 = df_all.groupby("barrio")["price_per_m2"].mean().sort_values(ascending=False).reset_index()
    fig_resumen = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE, color="barrio", title="€/m² medio por barrio")
    parts.append(fig_html(fig_resumen))

    # Por barrio
    for i, barrio_slug in enumerate(barrios_unicos):
        df = df_all[df_all['barrio']==barrio_slug]
        if df.empty: continue
        color = PALETTE[i % len(PALETTE)]
        barrio_nombre_original = barrio_slug.replace('-', ' ').title()
        parts.append(f"<h2>{{barrio_nombre_original}}</h2>")
        # Mapa
        mapa_html = generar_mapa_barrio_folium(barrio_nombre_original, geojson_gdf, df)
        parts.append(mapa_html)
        # Histogramas
        parts.append(histograma(df, "price", "Distribución de Precio (€)", color))
        parts.append(histograma(df, "price_per_m2", "Distribución de €/m²", color))
        parts.append(histograma(df, "size", "Distribución de Tamaño (m²)", color))
        # Scatter
        parts.append(scatter_precio_size(df, color))
        # Tablas
        cols_order = ['price', 'size', 'price_per_m2', 'rooms', 'exterior_label', 'lift_label', 'url']
        parts.append(tabla_html(df, "Top 10 — Más baratas (por €/m²)", "price_per_m2", True, cols_order))
        parts.append(tabla_html(df, "Top 10 — Más caras (por €/m²)", "price_per_m2", False, cols_order))
    parts.append("</body></html>")
    return "".join(parts)

# ==============================
# Main
# ==============================
def main():
    print("DEBUG: Iniciando el proceso principal...")
    try:
        # Cargar el archivo GeoJSON de barrios de Madrid
        geojson_gdf = gpd.read_file("BARRIOS.shp")
        if 'NOMBRE' in geojson_gdf.columns:
            nombre_col = 'NOMBRE'
        elif 'BARRIO_MAY' in geojson_gdf.columns:
            nombre_col = 'BARRIO_MAY'
        else:
            raise ValueError("No se encontró una columna de nombre de barrio en el SHP.")
        geojson_gdf['slug'] = geojson_gdf[nombre_col].apply(slugify)
        geojson_gdf['nombre'] = geojson_gdf[nombre_col]
        print("✅ Archivo GeoJSON de barrios de Madrid cargado con éxito.")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado con GeoJSON: {e}")
        return

    try:
        token = get_onedrive_token()
        print("✅ Token de OneDrive obtenido.")

        folders = list_folders(BASE_FOLDER, token)
        fechas = [f.get("name") for f in folders if isinstance(f, dict) and f.get("folder") and es_fecha(f.get("name", ''))]
        if not fechas:
            print("❌ No hay carpetas con formato fecha.")
            return
        fecha = sorted(fechas, reverse=True)[0]
        print(f"📁 Usando datos de la carpeta: {fecha}")

        carpeta_path = f"{BASE_FOLDER}/{fecha}"
        archivos = list_folders(carpeta_path, token)
        archivos_xlsx = [a for a in archivos if isinstance(a, dict) and a.get("name") and a["name"].lower().endswith(".xlsx")]
        if not archivos_xlsx:
            print(f"❌ No se encontraron archivos Excel en la carpeta {fecha}.")
            return

        barrios, dfs = [], []
        for a in sorted(archivos_xlsx, key=lambda x: x['name']):
            barrio_nombre_original = os.path.splitext(a["name"])[0]
            file_path = f"{carpeta_path}/{a['name']}"
            try:
                print(f"📥 Descargando y procesando: {a['name']}")
                df = download_excel(file_path, token)
                
                # Definir las columnas que deben estar presentes
                required_cols = ['price', 'size', 'rooms', 'exterior', 'hasLift', 'latitude', 'longitude', 'url']
                
                # Verificar si el DataFrame tiene todas las columnas requeridas
                if not all(col in df.columns for col in required_cols):
                    print(f"⚠️ El archivo {a['name']} no tiene todas las columnas requeridas. Saltando.")
                    continue
                
                # Limpieza y cálculos
                df_limpio = df[required_cols].copy()
                df_limpio = df_limpio[(df_limpio['size'].notna()) & (df_limpio['size'] > 0) & 
                                      (df_limpio['price'].notna()) & (df_limpio['price'] > 0)].copy()

                if df_limpio.empty:
                    print(f"⚠️ El archivo {a['name']} está vacío después de la limpieza. Saltando.")
                    continue
                
                df_limpio['price_per_m2'] = df_limpio['price'] / df_limpio['size']
                df_limpio['exterior_label'] = df_limpio['exterior'].apply(lambda x: 'Exterior' if x else 'Interior')
                df_limpio['lift_label'] = df_limpio['hasLift'].apply(lambda x: 'Con Ascensor' if x else 'Sin Ascensor')

                barrios.append(barrio_nombre_original)
                dfs.append(df_limpio)
            except Exception as e:
                print(f"⚠️ Error inesperado al procesar {a['name']}: {e}")

        if not dfs:
            print("❌ No se pudieron procesar los datos.")
            return

        print("\n📊 Generando informe HTML y JSON de datos...")
        full_html = generar_informe_global(dfs, barrios, fecha, geojson_gdf)
        out_path = os.environ.get("OUTPUT_FOLDER", "output_html")
        os.makedirs(out_path, exist_ok=True)
        out_file_path = os.path.join(out_path, "informe_semanal.html")
        with open(out_file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"✅ Informe generado: {out_file_path}")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")
        # Intentar imprimir un mensaje de error más específico si es posible
        print(f"Tipo de error: {type(e).__name__}, Detalles: {e}")

if __name__ == "__main__":
    main()
