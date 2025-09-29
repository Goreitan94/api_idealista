import os
import re
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO
import geopandas as gpd
import unicodedata

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
    data = {"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "scope": "https://graph.microsoft.com/.default"}
    response = requests.post(token_url, data=data)
    token_data = response.json()
    if "access_token" in token_data:
        return token_data["access_token"]
    else:
        raise RuntimeError(f"No se pudo obtener token: {token_data}")

def list_folders(path, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{path}:/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json().get("value", [])

def download_excel(path, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{path}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
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
        return f"€{x:,.0f}".replace(",", ".")
    except:
        return ""

def fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=True, config={"displaylogo": False, "modeBarButtonsToRemove": ["select", "lasso2d", "hovercompare"], "scrollZoom": True, "responsive": True})

# ==============================
# Gráficos y Tablas Helpers
# ==============================
def generar_mapa_barrio(barrio_nombre, geojson_gdf, df_barrio):
    print(f"\n🗺️ Iniciando generación de mapa para el barrio: '{barrio_nombre}'")
    barrio_slug = slugify(barrio_nombre)
    barrio_seleccionado_gdf = geojson_gdf[geojson_gdf['slug'] == barrio_slug].copy()
    
    df_mapa = geojson_gdf.copy()
    df_mapa['color_del_mapa'] = '#404040' 
    df_mapa['nombre_para_hover'] = df_mapa['nombre']
    
    border_width = [1] * len(df_mapa)
    border_color = ['rgba(255,255,255,0.2)'] * len(df_mapa)
    
    center = {"lat": 40.4168, "lon": -3.7038}
    zoom_level = 9.5
    
    if not barrio_seleccionado_gdf.empty:
        print("✅ Polígono del barrio encontrado en el GeoJSON.")
        # Paso crucial: convertimos el GeoDataFrame a WGS84 (EPSG:4326) para obtener coordenadas de lat/lon
        barrio_seleccionado_wgs84 = barrio_seleccionado_gdf.to_crs(epsg=4326)
        
        idx_selected = barrio_seleccionado_gdf.index[0]
        df_mapa.loc[idx_selected, 'color_del_mapa'] = PALETTE[0]
        border_width[idx_selected] = 2
        border_color[idx_selected] = 'white'
        
        centroid = barrio_seleccionado_wgs84.geometry.iloc[0].centroid
        center = {"lat": centroid.y, "lon": centroid.x}
        
        area = barrio_seleccionado_gdf.geometry.iloc[0].area
        zoom_level = max(11, min(15, 16 - np.log10(area * 1000000)))
        print(f"✅ Centro del mapa calculado a partir del GeoJSON. Lat: {center['lat']:.2f}, Lon: {center['lon']:.2f}, Zoom: {zoom_level:.2f}")
    else:
        print(f"⚠️ Polígono del barrio no encontrado en el GeoJSON. Intentando usar coordenadas de los datos.")
        if not df_barrio.empty and 'latitude' in df_barrio.columns and 'longitude' in df_barrio.columns:
            center = {"lat": df_barrio['latitude'].mean(), "lon": df_barrio['longitude'].mean()}
            zoom_level = 11.5
            print(f"✅ Centro del mapa calculado a partir de los datos. Lat: {center['lat']:.2f}, Lon: {center['lon']:.2f}, Zoom: {zoom_level:.2f}")
        else:
            center = {"lat": 40.4168, "lon": -3.7038}
            zoom_level = 9.5
            print("❌ No hay coordenadas en los datos. Usando el centro por defecto de Madrid.")

    fig = go.Figure()

    print("🖼️ Añadiendo trazo de polígonos al mapa.")
    choropleth_trace = px.choropleth_mapbox(
        df_mapa,
        geojson=df_mapa.geometry,
        locations=df_mapa.index,
        color='color_del_mapa',
        custom_data=['nombre_para_hover']
    ).data[0]
    
    choropleth_trace.marker.line.width = border_width
    choropleth_trace.marker.line.color = border_color
    
    fig.add_trace(choropleth_trace)

    if not df_barrio.empty and 'latitude' in df_barrio.columns and 'longitude' in df_barrio.columns:
        print(f"📌 Añadiendo {len(df_barrio)} puntos de inmuebles al mapa.")
        fig.add_trace(go.Scattermapbox(
            lat=df_barrio['latitude'],
            lon=df_barrio['longitude'],
            mode='markers',
            marker=go.scattermapbox.Marker(
                size=8,
                color=PALETTE[3],
                opacity=0.7,
                symbol='circle'
            ),
            hovertext=df_barrio['price'].apply(fmt_eur) + ' | ' + df_barrio['size'].astype(str) + ' m²',
            hoverinfo='text',
            name='Inmuebles'
        ))

    else:
        print("❌ No se encontraron datos de latitud/longitud en el DataFrame del barrio. No se añadirán puntos.")

    fig.update_layout(
        title="",
        margin={"r":0,"t":0,"l":0,"b":0},
        mapbox_style="carto-positron",
        mapbox_zoom=zoom_level,
        mapbox_center=center,
        showlegend=False,
        height=400
    )
    
    print("✅ Mapa generado correctamente.")
    return fig_html(fig)

def histograma(df, col, title, color):
    if col not in df.columns or df[col].dropna().empty: return ""
    fig = px.histogram(df, x=col, nbins=30, template=TEMPLATE, title=title)
    fig.update_traces(marker_color=color, opacity=0.9, marker_line_color='rgb(255,255,255)', marker_line_width=0.5)
    return fig_html(fig)

def scatter_precio_size(df, color):
    if not set(["price", "size"]).issubset(df.columns) or df[["price","size"]].dropna().empty: return ""
    fig = px.scatter(df, x="size", y="price", template=TEMPLATE, title="Relación Precio vs Tamaño", hover_data=["rooms","price_per_m2"])
    fig.update_traces(marker=dict(size=8, line=dict(width=0.5, color="rgba(255,255,255,0.4)"), color=color), opacity=0.7)
    clean = df[["size","price"]].dropna()
    if len(clean) >= 2:
        m, b = np.polyfit(clean["size"], clean["price"], 1)
        x_line = np.linspace(clean["size"].min(), clean["size"].max(), 50)
        y_line = m * x_line + b
        fig.add_trace(go.Scatter(x=x_line, y=y_line, mode="lines", name="Tendencia", line=dict(width=2)))
    return fig_html(fig)

def scatter_price_size_trend(df, title, color):
    if not set(["price_per_m2", "size"]).issubset(df.columns) or df[["price_per_m2","size"]].dropna().empty: return ""
    fig = px.scatter(
        df, x="size", y="price_per_m2", title=title, template=TEMPLATE,
        color_discrete_sequence=[color], hover_data=["price", "rooms"],
        opacity=0.6, trendline="lowess", trendline_options=dict(frac=0.3)
    )
    fig.update_traces(marker=dict(size=6, line=dict(width=0.5, color='rgba(255,255,255,0.4)')))
    fig.update_layout(xaxis_title="Tamaño (m²)", yaxis_title="Precio por m² (€/m²)", hovermode="x unified")
    return fig_html(fig)

def bar_chart_features(df, title, color):
    if "exterior_label" not in df.columns or "lift_label" not in df.columns or df.empty: return ""
    df_grouped = df.groupby(['exterior_label', 'lift_label'])['price_per_m2'].mean().reset_index()
    df_grouped['category'] = df_grouped['exterior_label'] + ' / ' + df_grouped['lift_label']
    custom_order = ['Exterior / Con Ascensor', 'Exterior / Sin Ascensor', 'Interior / Con Ascensor', 'Interior / Sin Ascensor']
    df_grouped['category'] = pd.Categorical(df_grouped['category'], categories=custom_order, ordered=True)
    df_grouped = df_grouped.sort_values('category')
    fig = px.bar(
        df_grouped, x="category", y="price_per_m2", title=title, template=TEMPLATE,
        color='exterior_label', color_discrete_map={'Exterior': color, 'Interior': 'rgba(255,255,255,0.4)'}
    )
    fig.update_layout(xaxis_title="", yaxis_title="€/m² Medio", legend_title_text="Tipo de Vivienda")
    return fig_html(fig)

def bar_chart_lift_impact(df, title, color_lift_true='#6c9ef8', color_lift_false='rgba(255,255,255,0.4)'):
    if "lift_label" not in df.columns or df["lift_label"].dropna().empty: return ""
    df_grouped = df.groupby("lift_label")["price_per_m2"].mean().reset_index()
    df_grouped['lift_label'] = pd.Categorical(df_grouped['lift_label'], categories=['Con Ascensor', 'Sin Ascensor'], ordered=True)
    df_grouped = df_grouped.sort_values('lift_label')
    fig = px.bar(
        df_grouped, x="lift_label", y="price_per_m2", title=title, template=TEMPLATE,
        color="lift_label", color_discrete_map={'Con Ascensor': color_lift_true, 'Sin Ascensor': color_lift_false},
        text="price_per_m2"
    )
    fig.update_traces(texttemplate='%{text:,.0f}€/m²', textposition='outside')
    fig.update_layout(xaxis_title="", yaxis_title="€/m² Medio", uniformtext_minsize=8, uniformtext_mode='hide', showlegend=False)
    fig.update_yaxes(range=[0, df_grouped["price_per_m2"].max() * 1.2])
    return fig_html(fig)

def bar_price_exterior(df, title, color_exterior='#6c9ef8', color_interior='rgba(255,255,255,0.4)'):
    if "exterior_label" not in df.columns or df["price_per_m2"].dropna().empty: return ""
    df_grouped = df.groupby("exterior_label")["price_per_m2"].mean().reset_index()
    order = ['Exterior', 'Interior']
    df_grouped['exterior_label'] = pd.Categorical(df_grouped['exterior_label'], categories=order, ordered=True)
    df_grouped = df_grouped.sort_values('exterior_label')
    fig = px.bar(
        df_grouped, x="exterior_label", y="price_per_m2", title=title, template=TEMPLATE,
        color='exterior_label', color_discrete_map={'Exterior': color_exterior, 'Interior': color_interior},
        text='price_per_m2'
    )
    fig.update_traces(texttemplate='%{text:,.0f}€/m²', textposition='outside')
    fig.update_layout(yaxis_title="€/m² Medio", showlegend=False)
    return fig_html(fig)

def tabla_html(df, title, sort_col, ascending, cols_order):
    usable = df.copy().sort_values(sort_col, ascending=ascending).head(10)
    if 'url' in df.columns and 'url' not in cols_order:
        cols_order.append('url')

    usable = usable[[c for c in cols_order if c in usable.columns]]
    if usable.empty:
        return ""

    header_html = "".join([f"<th>{c.replace('_', ' ').title().replace('Url', 'Anuncio')}</th>" for c in usable.columns])
    
    rows_html = ""
    for index, row in usable.iterrows():
        cells_html = ""
        for c in usable.columns:
            val = row[c]
            if c == "price":
                val = fmt_eur(val)
            elif c == "price_per_m2":
                val = f"{val:,.2f} €/m²".replace(",", "X").replace(".", ",").replace("X", ".") # Formateo a 2 decimales
            elif c == "size":
                val = f"{int(val):,} m²".replace(",", ".")
            elif c == "url":
                val = f"<a href='{val}' target='_blank'>Ver Anuncio</a>"
            else:
                val = str(val)
            cells_html += f"<td>{val}</td>"
        rows_html += f"<tr>{cells_html}</tr>"

    html = f"""
    <div style="background:transparent; padding:0; margin-bottom:14px;">
        <h2 style="font-size:18px; text-align:center; margin:8px 6px 10px;">{title}</h2>
        <div style="max-height: 400px; overflow-y: auto;">
        <table style="width:100%; border-collapse:collapse; text-align:center;">
            <thead>
                <tr style="background-color:#1a2445; color:white;">{header_html}</tr>
            </thead>
            <tbody style="background-color:#121a33; color:white;">
                {rows_html}
            </tbody>
        </table>
        </div>
    </div>
    """
    return html

# ==============================
# Generador de Informe
# ==============================
def generar_informe_global(all_dfs: list[pd.DataFrame], barrios: list[str], fecha: str, geojson_gdf):
    parts = [f"""
<!doctype html><html lang="es"><head><meta charset="utf-8" /><title>UrbenEye — Informe Interactivo — {fecha}</title><meta name="viewport" content="width=device-width, initial-scale=1" /><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script><style>:root{{--bg:#0b1020;--card:#121a33;--ink:#e6ecff;--muted:#a8b2d1;--accent:#6c9ef8;}}html,body{{background:var(--bg);color:var(--ink);font-family:system-ui,-apple-syste...""" ]
    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty: continue
        tmp = df.copy()
        tmp["barrio"] = barrio
        df_all.append(tmp)

    if not df_all:
        parts.append("<p>No hay datos.</p></div></body></html>")
        return "".join(parts)
        
    df_all = pd.concat(df_all, ignore_index=True)
    
    barrios_unicos = df_all['barrio'].unique().tolist()
    
    parts.append("""...
    .toc a.pill{color:#081229;background:#cfe1ff;border-radius:999px;padding:6px 12px;font-size:13px;text-decoration:none;display:inline-block;} 
    .toc a.pill:hover{background:#9fc9ff;color:#03112a;text-decoration:none;}
    .section{background:var(--card);border:1px solid rgba(255,255,255,0.06);border-radius:18px;padding:14px;margin:14px 0 22px;} .section > h2{font-size:20px;margin:8px 6px 10px;} .pill{display:inline-block;font-size:12px;color:#081229;background:#cfe1ff;border-radius:999px;padding:2px 10px;margin-left:8px;} .pill a{color:#081229;text-decoration:none;} .pill a:hover{color:#004488;} .grid{display:grid;grid-template-columns:1fr;gap:14px;} @media(min-width:900px){.grid-2{grid-template-columns:1fr 1fr;} .grid-3{grid-template-columns:1fr 1fr 1fr;}} .anchor{scroll-margin-top:20px;}</style></head><body><div class="wrap"><div class="hero"><h1>📊 UrbenEye — Informe Interactivo — """ + fecha + """</h1><div class="sub">Fuente: Idealista API | Generado Automáticamente</div></div>
    ...""")
    
    parts.append('<div class="toc"><h3>Navegación</h3><div style="display:flex;flex-wrap:wrap;gap:10px;"><a href="#resumen" class="pill">Resumen general</a>')
    for b_slug in barrios_unicos: parts.append(f'<a href="#{b_slug}" class="pill">{b_slug.replace("-", " ").title()}</a>')
    parts.append('</div></div>')
    
    parts.append('<div id="resumen" class="section anchor"><h2>📌 Resumen general</h2>')
    m_ppm2 = df_all.groupby("barrio")["price_per_m2"].mean().sort_values(ascending=False).reset_index()
    fig_resumen1 = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE, title="€/m² medio por barrio", color="barrio")
    parts.append(fig_html(fig_resumen1))
    parts.append('</div>')

    for i, barrio_slug in enumerate(barrios_unicos):
        df = df_all[df_all["barrio"] == barrio_slug]
        if df.empty: continue
        color = PALETTE[i % len(PALETTE)]
        
        barrio_nombre_original = barrio_slug.replace('-', ' ').title()
        
        parts.append(f'<div id="{barrio_slug}" class="section anchor"><h2>🏘️ {barrio_nombre_original}</h2><div class="grid grid-3">')
        
        mapa_html = generar_mapa_barrio(barrio_nombre_original, geojson_gdf, df)
        if mapa_html:
            parts.append(f'<div style="grid-column: span 3; border-radius:10px; overflow:hidden;">{mapa_html}</div>')
        
        parts.append(histograma(df, "price", "Distribución de Precio (€)", color))
        parts.append(histograma(df, "price_per_m2", "Distribución de €/m²", color))
        parts.append(histograma(df, "size", "Distribución de Tamaño (m²)", color))
        parts.append('</div><div class="grid grid-2">')
        parts.append(scatter_precio_size(df, color))
        parts.append(scatter_price_size_trend(df, "€/m² vs Tamaño: Tendencia no lineal", color))
        parts.append(bar_chart_features(df, "€/m² Medio: Exterior vs Interior / Con vs Sin Ascensor", color))
        parts.append(bar_price_exterior(df, "€/m² Medio: Exterior vs Interior"))
        parts.append(bar_chart_lift_impact(df, "€/m² Medio: Con vs Sin Ascensor", color))
        parts.append('</div><div class="grid grid-2">')
        cols_order = ['price', 'size', 'price_per_m2', 'rooms', 'exterior_label', 'lift_label', 'url']
        parts.append(tabla_html(df, "Top 10 — Más baratas (por €/m²)", "price_per_m2", True, cols_order))
        parts.append(tabla_html(df, "Top 10 — Más caras (por €/m²)", "price_per_m2", False, cols_order))
        parts.append('</div></div>')
        
    parts.append("</div></body></html>")
    return "".join(parts)

# ==============================
# Main
# ==============================
def main():
    try:
        geojson_gdf = gpd.read_file("BARRIOS.shp")
        if 'NOMBRE' in geojson_gdf.columns:
            nombre_col = 'NOMBRE'
        elif 'BARRIO_MAY' in geojson_gdf.columns:
            nombre_col = 'BARRIO_MAY'
        else:
            raise ValueError("No se encontró una columna de nombre de barrio en el SHP. Por favor, revisa el archivo.")

        geojson_gdf['slug'] = geojson_gdf[nombre_col].apply(slugify)
        geojson_gdf['nombre'] = geojson_gdf[nombre_col]
        print("✅ Archivo GeoJSON de barrios de Madrid cargado.")
    except Exception as e:
        print(f"❌ Error al cargar el archivo GeoJSON: {e}")
        print("❌ Asegúrate de tener todos los archivos SHP en la misma carpeta e instalado 'geopandas'.")
        geojson_gdf = None
        return

    token = get_onedrive_token()
    print("✅ Token de OneDrive obtenido.")

    folders = list_folders(BASE_FOLDER, token)
    fechas = [f["name"] for f in folders if f.get("folder") and es_fecha(f["name"])]
    if not fechas:
        print("❌ No hay carpetas con formato fecha.")
        return
    fecha = sorted(fechas, reverse=True)[0]
    print(f"📁 Usando datos de la carpeta: {fecha}")

    carpeta_path = f"{BASE_FOLDER}/{fecha}"
    archivos = list_folders(carpeta_path, token)
    archivos_xlsx = [a for a in archivos if a["name"].lower().endswith(".xlsx")]
    if not archivos_xlsx:
        print(f"❌ No se encontraron archivos Excel en la carpeta {fecha}.")
        return

    barrios, dfs = [], []
    for a in sorted(archivos_xlsx, key=lambda x: x['name']):
        barrio_nombre_original = os.path.splitext(a["name"])[0]
        barrio_slug = slugify(barrio_nombre_original)
        file_path = f"{carpeta_path}/{a['name']}"
        try:
            print(f"📥 Descargando y procesando: {a['name']}")
            df = download_excel(file_path, token)
            if 'size' in df.columns: df = df[df['size'] > 0].copy()
            if 'price' in df.columns: df = df[df['price'] > 0].copy()
            if 'size' in df.columns and 'price' in df.columns:
                df['price_per_m2'] = df['price'] / df['size'].replace(0, np.nan)
                # === APLICACIÓN DEL REDONDEO ===
                df['price_per_m2'] = df['price_per_m2'].round(2)
                # ===============================
            if 'exterior' in df.columns:
                df['exterior_label'] = df['exterior'].apply(lambda x: 'Exterior' if x else 'Interior')
            if 'hasLift' in df.columns:
                df['lift_label'] = df['hasLift'].apply(lambda x: 'Con Ascensor' if x else 'Sin Ascensor')
            
            barrios.append(barrio_slug)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ Error procesando {a['name']}: {e}")

    print("\n📊 Generando informe HTML completo...")
    full_html = generar_informe_global(dfs, barrios, fecha, geojson_gdf)

    out_folder_pages = os.environ.get("OUTPUT_FOLDER", "output_html")
    os.makedirs(out_folder_pages, exist_ok=True)
    out_path_pages = os.path.join(out_folder_pages, "index.html")
    with open(out_path_pages, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe final guardado en '{out_path_pages}' para su despliegue.")

if __name__ == "__main__":
    main()
