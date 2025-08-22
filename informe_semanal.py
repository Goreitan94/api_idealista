import os
import re
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO

# ==============================
# Config
# ==============================
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

BASE_FOLDER = "/Idealista API (Datos)/Datos"   # carpeta en OneDrive
TEMPLATE = "plotly_white"
PALETTE = px.colors.qualitative.Prism  # colores vivos y variados

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

def fmt_eur(x):
    try:
        return f"€{x:,.0f}".replace(",", ".")
    except:
        return ""

def fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={
        "displaylogo": False, "modeBarButtonsToRemove": ["select", "lasso2d"]
    })

# ==============================
# Gráficos helpers
# ==============================
def histograma(df, col, title, color):
    if col not in df.columns or df[col].dropna().empty:
        return ""
    fig = px.histogram(df, x=col, nbins=30, template=TEMPLATE, title=title)
    fig.update_traces(marker_color=color, opacity=0.9)
    return fig_html(fig)

def scatter_precio_size(df, color):
    if not set(["price", "size"]).issubset(df.columns) or df[["price","size"]].dropna().empty:
        return ""
    fig = px.scatter(
        df, x="size", y="price", template=TEMPLATE,
        title="Relación Precio vs Tamaño (con línea de tendencia)",
        hover_data=["rooms","price_per_m2"] if "rooms" in df.columns else ["price_per_m2"]
    )
    fig.update_traces(marker=dict(size=8, line=dict(width=0.5, color="rgba(0,0,0,.4)"), color=color), opacity=0.7)
    clean = df[["size","price"]].dropna()
    if len(clean) >= 2:
        m, b = np.polyfit(clean["size"], clean["price"], 1)
        x_line = np.linspace(clean["size"].min(), clean["size"].max(), 50)
        y_line = m * x_line + b
        fig.add_trace(go.Scatter(x=x_line, y=y_line, mode="lines",
                                 name="Tendencia", line=dict(width=2)))
    return fig_html(fig)

# ==============================
# Informe
# ==============================
def generar_informe_global(all_dfs, barrios, fecha):
    parts = [f"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>Informe Interactivo — {fecha}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
</head>
<body>
<div class="wrap">
  <h1>📊 Informe Interactivo — {fecha}</h1>
"""]

    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is not None and not df.empty:
            tmp = df.copy()
            tmp["barrio"] = barrio
            df_all.append(tmp)
    if df_all:
        df_all = pd.concat(df_all, ignore_index=True)
    else:
        parts.append("<p>No hay datos.</p></div></body></html>")
        return "".join(parts)

    if "price_per_m2" in df_all.columns:
        m_ppm2 = df_all.groupby("barrio")["price_per_m2"].mean().reset_index()
        fig = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE,
                     title="€/m² medio por barrio", color="barrio",
                     color_discrete_sequence=PALETTE)
        parts.append(fig_html(fig))

    parts.append("</div></body></html>")
    return "".join(parts)

# ==============================
# Main
# ==============================
def main():
    token = get_onedrive_token()

    # 1. listar carpetas en BASE_FOLDER
    folders = list_folders(BASE_FOLDER, token)
    fechas = [f["name"] for f in folders if f.get("folder") and es_fecha(f["name"])]
    if not fechas:
        print("❌ No hay carpetas con formato fecha.")
        return
    fecha = sorted(fechas, reverse=True)[0]
    print(f"📁 Carpeta más reciente: {fecha}")

    # 2. listar xlsx dentro de esa carpeta
    carpeta_path = f"{BASE_FOLDER}/{fecha}"
    archivos = list_folders(carpeta_path, token)
    archivos_xlsx = [a for a in archivos if a["name"].lower().endswith(".xlsx")]
    if not archivos_xlsx:
        print("❌ No hay archivos Excel en la carpeta.")
        return

    barrios, dfs = [], []
    for a in archivos_xlsx:
        barrio = os.path.splitext(a["name"])[0]
        file_path = f"{carpeta_path}/{a['name']}"
        try:
            df = download_excel(file_path, token)
            if 'size' in df.columns and 'price' in df.columns:
                df = df[(df['size'] > 0) & (df['price'] > 0)].copy()
                df['price_per_m2'] = df['price'] / df['size'].replace(0, np.nan)
            barrios.append(barrio)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ Error en {a['name']}: {e}")

    # 3. generar informe
    full_html = generar_informe_global(dfs, barrios, fecha)

    # 4. guardar para GitHub Pages
    out_folder_pages = os.environ.get("OUTPUT_FOLDER", "output_html")
    os.makedirs(out_folder_pages, exist_ok=True)
    out_path_pages = os.path.join(out_folder_pages, "index.html")
    with open(out_path_pages, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe global guardado en {out_path_pages}")

if __name__ == "__main__":
    main()
