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
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
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
    text = text.lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return text

def fmt_eur(x):
    try:
        return f"€{x:,.0f}".replace(",", ".")
    except:
        return ""

def fig_html(fig) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "modeBarButtonsToRemove": ["select", "lasso2d"]}
    )

# ==============================
# Generar mapa del barrio
# ==============================
def generar_mapa_barrio(barrio_nombre, geojson_gdf):
    df_mapa = geojson_gdf.copy()
    df_mapa['color_del_mapa'] = '#404040'

    barrio_slug = slugify(barrio_nombre)
    df_mapa.loc[df_mapa['slug'] == barrio_slug, 'color_del_mapa'] = PALETTE[0]

    fig = px.choropleth_mapbox(
        df_mapa,
        geojson=df_mapa.__geo_interface__,
        locations='slug',
        color='color_del_mapa',
        featureidkey='properties.slug',
        center={"lat": 40.4168, "lon": -3.7038},
        zoom=10,
        opacity=0.7
    )

    fig.update_traces(marker_line_width=1, marker_line_color='rgba(255,255,255,0.2)')
    fig.update_layout(
        mapbox_style="carto-positron",  # O "open-street-map" si no tienes token de Mapbox
        margin={"r":0,"t":0,"l":0,"b":0},
        showlegend=False
    )
    fig.update_traces(hovertemplate='<b>%{properties.nombre}</b><extra></extra>')

    return fig_html(fig)

# ==============================
# Gráficos y Tablas Helpers
# ==============================
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
        df,
        x="size",
        y="price_per_m2",
        title=title,
        template=TEMPLATE,
        color_discrete_sequence=[color],
        hover_data=["price", "rooms"],
        opacity=0.6,
        trendline="lowess",
        trendline_options=dict(frac=0.3)
    )
    fig.update_traces(marker=dict(size=6, line=dict(width=0.5, color='rgba(255,255,255,0.4)')))
    fig.update_layout(
        xaxis_title="Tamaño (m²)",
        yaxis_title="Precio por m² (€/m²)",
        hovermode="x unified"
    )
    return fig_html(fig)

def bar_chart_features(df, title, color):
    if "exterior_label" not in df.columns or "lift_label" not in df.columns or df.empty:
        return ""
    df_grouped = df.groupby(['exterior_label', 'lift_label'])['price_per_m2'].mean().reset_index()
    df_grouped['category'] = df_grouped['exterior_label'] + ' / ' + df_grouped['lift_label']
    custom_order = ['Exterior / Con Ascensor', 'Exterior / Sin Ascensor', 'Interior / Con Ascensor', 'Interior / Sin Ascensor']
    df_grouped['category'] = pd.Categorical(df_grouped['category'], categories=custom_order, ordered=True)
    df_grouped = df_grouped.sort_values('category')
    fig = px.bar(
        df_grouped,
        x="category",
        y="price_per_m2",
        title=title,
        template=TEMPLATE,
        color='exterior_label',
        color_discrete_map={'Exterior': color, 'Interior': 'rgba(255,255,255,0.4)'}
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="€/m² Medio",
        legend_title_text="Tipo de Vivienda",
    )
    return fig_html(fig)

def bar_chart_lift_impact(df, title, color_lift_true='#6c9ef8', color_lift_false='rgba(255,255,255,0.4)'):
    if "lift_label" not in df.columns or df["lift_label"].dropna().empty:
        return ""
    df_grouped = df.groupby("lift_label")["price_per_m2"].mean().reset_index()
    df_grouped['lift_label'] = pd.Categorical(df_grouped['lift_label'], categories=['Con Ascensor', 'Sin Ascensor'], ordered=True)
    df_grouped = df_grouped.sort_values('lift_label')
    fig = px.bar(
        df_grouped,
        x="lift_label",
        y="price_per_m2",
        title=title,
        template=TEMPLATE,
        color="lift_label",
        color_discrete_map={'Con Ascensor': color_lift_true, 'Sin Ascensor': color_lift_false},
        text="price_per_m2"
    )
    fig.update_traces(texttemplate='%{text:,.0f}€/m²', textposition='outside')
    fig.update_layout(
        xaxis_title="",
        yaxis_title="€/m² Medio",
        uniformtext_minsize=8, uniformtext_mode='hide',
        showlegend=False
    )
    fig.update_yaxes(range=[0, df_grouped["price_per_m2"].max() * 1.2])
    return fig_html(fig)

def bar_price_exterior(df, title, color_exterior='#6c9ef8', color_interior='rgba(255,255,255,0.4)'):
    if "exterior_label" not in df.columns or df["price_per_m2"].dropna().empty:
        return ""
    df_grouped = df.groupby("exterior_label")["price_per_m2"].mean().reset_index()
    order = ['Exterior', 'Interior']
    df_grouped['exterior_label'] = pd.Categorical(df_grouped['exterior_label'], categories=order, ordered=True)
    df_grouped = df_grouped.sort_values('exterior_label')
    fig = px.bar(
        df_grouped,
        x="exterior_label",
        y="price_per_m2",
        title=title,
        template=TEMPLATE,
        color='exterior_label',
        color_discrete_map={'Exterior': color_exterior, 'Interior': color_interior},
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
    for _, row in usable.iterrows():
        cells_html = ""
        for c in usable.columns:
            val = row[c]
            if c == "price":
                val = fmt_eur(val)
            elif c == "price_per_m2":
                val = f"{fmt_eur(val)}/m²"
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
<!doctype html><html lang="es"><head><meta charset="utf-8" /><title>UrbenEye — Informe Interactivo — {fecha}</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script></head><body><div class="wrap">
<h1>📊 UrbenEye — Informe Interactivo — {fecha}</h1>"""]

    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty:
            continue
        tmp = df.copy()
        tmp["barrio"] = re.sub(r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$', '', barrio)
        df_all.append(tmp)

    if not df_all:
        parts.append("<p>No hay datos.</p></div></body></html>")
        return "".join(parts)

    df_all = pd.concat(df_all, ignore_index=True)
    barrios_unicos = df_all["barrio"].unique().tolist()

    for i, barrio_nombre in enumerate(barrios_unicos):
        df = df_all[df_all["barrio"] == barrio_nombre]
        if df.empty: continue
        color = PALETTE[i % len(PALETTE)]
        parts.append(f"<h2>{barrio_nombre}</h2>")
        mapa_html = generar_mapa_barrio(barrio_nombre, geojson_gdf)
        if mapa_html:
            parts.append(mapa_html)
        parts.append(histograma(df, "price", "Distribución de Precio (€)", color))

    parts.append("</div></body></html>")
    return "".join(parts)

# ==============================
# Main
# ==============================
def main():
    try:
        geojson_gdf = gpd.read_file("BARRIOS.shp")
        geojson_gdf.rename(columns={'NOMBRE': 'nombre'}, inplace=True)
        geojson_gdf['slug'] = geojson_gdf['nombre'].apply(slugify)
        print("✅ Archivo GeoJSON de barrios de Madrid cargado.")
    except Exception as e:
        print(f"❌ Error al cargar el archivo GeoJSON: {e}")
        return

    token = get_onedrive_token()
    print("✅ Token de OneDrive obtenido.")

    folders = list_folders(BASE_FOLDER, token)
    fechas = [f["name"] for f in folders if f.get("folder") and es_fecha(f["name"])]
    if not fechas:
        print("❌ No hay carpetas con formato fecha.")
        return
    fecha = sorted(fechas, reverse=True)[0]
    carpeta_path = f"{BASE_FOLDER}/{fecha}"
    archivos = list_folders(carpeta_path, token)
    archivos_xlsx = [a for a in archivos if a["name"].lower().endswith(".xlsx")]

    barrios, dfs = [], []
    for a in sorted(archivos_xlsx, key=lambda x: x['name']):
        barrio_nombre = os.path.splitext(a["name"])[0]
        file_path = f"{carpeta_path}/{a['name']}"
        try:
            df = download_excel(file_path, token)
            if 'size' in df.columns: df = df[df['size'] > 0].copy()
            if 'price' in df.columns: df = df[df['price'] > 0].copy()
            if 'size' in df.columns and 'price' in df.columns:
                df['price_per_m2'] = df['price'] / df['size'].replace(0, np.nan)
            if 'exterior' in df.columns:
                df['exterior_label'] = df['exterior'].apply(lambda x: 'Exterior' if x else 'Interior')
            if 'hasLift' in df.columns:
                df['lift_label'] = df['hasLift'].apply(lambda x: 'Con Ascensor' if x else 'Sin Ascensor')
            barrios.append(barrio_nombre)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ Error procesando {a['name']}: {e}")

    print("📊 Generando informe HTML completo...")
    full_html = generar_informe_global(dfs, barrios, fecha, geojson_gdf)
    os.makedirs("output_html", exist_ok=True)
    out_path = os.path.join("output_html", "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe final guardado en '{out_path}'.")

if __name__ == "__main__":
    main()
