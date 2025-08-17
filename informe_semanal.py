import os
import re
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ==============================
# Config
# ==============================
BASE_FOLDER = "/Users/eitangorenberg/Library/CloudStorage/OneDrive-UrbenEye/Idealista API (Datos)/Datos"
TEMPLATE = "plotly_white"
PALETTE = px.colors.qualitative.Prism  # colores vivos y variados

# ==============================
# Utilidades
# ==============================
def es_fecha(nombre: str) -> bool:
    try:
        datetime.strptime(nombre, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def get_latest_folder(base_folder: str) -> str | None:
    folders = [f for f in os.listdir(base_folder)
               if os.path.isdir(os.path.join(base_folder, f)) and es_fecha(f)]
    if not folders:
        print("❌ No hay carpetas con fecha en formato YYYY-MM-DD.")
        return None
    folders.sort(reverse=True)
    path = os.path.join(base_folder, folders[0])
    print(f"📁 Carpeta elegida: {path}")
    return path

def cargar_excel(path: str) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(path)
        # limpieza básica
        if 'size' in df.columns:
            df = df[df['size'] > 0].copy()
        if 'price' in df.columns:
            df = df[df['price'] > 0].copy()

        # €/m2
        if 'size' in df.columns and 'price' in df.columns:
            df['price_per_m2'] = df['price'] / df['size'].replace(0, np.nan)
        else:
            df['price_per_m2'] = np.nan

        # etiquetas categóricas limpias
        if 'exterior' in df.columns:
            df['exterior_label'] = (
                df['exterior'].astype(str).str.lower().fillna('')
                .map(lambda x: 'Exterior' if x == 'true' else 'Interior')
            )
        if 'hasLift' in df.columns:
            df['lift_label'] = df['hasLift'].map(lambda x: 'Con Ascensor' if bool(x) else 'Sin Ascensor')
        if 'hasParking' in df.columns:
            df['parking_label'] = df['hasParking'].map(lambda x: 'Con Parking' if bool(x) else 'Sin Parking')

        # rooms a int cuando tenga sentido
        if 'rooms' in df.columns:
            with pd.option_context('mode.use_inf_as_na', True):
                df['rooms'] = pd.to_numeric(df['rooms'], errors='coerce')

        return df
    except Exception as e:
        print(f"⚠️ Error leyendo {path}: {e}")
        return None

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
    return fig.to_html(full_html=False, include_plotlyjs=False, config={
        "displaylogo": False, "modeBarButtonsToRemove": ["select", "lasso2d"]
    })

# ==============================
# Gráficos helpers (per barrio)
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

def tabla(df, title, sort_col, ascending, cols_order):
    usable = df.copy()
    for c in ["price","size","price_per_m2"]:
        if c in usable.columns:
            usable[c] = usable[c].round(0)
    usable = usable.sort_values(sort_col, ascending=ascending).head(10)
    usable = usable[[c for c in cols_order if c in usable.columns]]
    if usable.empty:
        return ""
    def col_vals(c):
        vals = usable[c].tolist()
        if c == "price":       vals = [fmt_eur(v) for v in vals]
        if c == "price_per_m2": vals = [fmt_eur(v)+"/m²" for v in vals]
        if c == "size":        vals = [f"{int(v):,} m²".replace(",", ".") for v in vals]
        return vals
    header = [c.replace("_"," ").title() for c in usable.columns]
    cells = [col_vals(c) for c in usable.columns]
    fig = go.Figure(data=[go.Table(
        header=dict(values=header, fill_color="#f1f3f5", align="center"),
        cells=dict(values=cells, align="center")
    )])
    return fig_html(fig)

# ==============================
# Informe (un solo HTML)
# ==============================
def generar_informe_global(all_dfs, barrios, fecha, output_folder):
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
        return

    # Un ejemplo de gráfico global
    if "price_per_m2" in df_all.columns:
        m_ppm2 = df_all.groupby("barrio")["price_per_m2"].mean().reset_index()
        fig = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE,
                     title="€/m² medio por barrio", color="barrio",
                     color_discrete_sequence=PALETTE)
        parts.append(fig_html(fig))

    # ---- Cierre ----
    parts.append("</div></body></html>")
    full_html = "".join(parts)

    # Guardar en OneDrive
    out_path_data = os.path.join(output_folder, f"informe_interactivo_{fecha}.html")
    with open(out_path_data, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe global guardado en datos: {out_path_data}")

    # Guardar en output_html (para GitHub Pages)
    out_folder_pages = os.environ.get("OUTPUT_FOLDER", "output_html")
    os.makedirs(out_folder_pages, exist_ok=True)
    out_path_pages = os.path.join(out_folder_pages, "index.html")
    with open(out_path_pages, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe global guardado para GitHub Pages: {out_path_pages}")

# ==============================
# Main
# ==============================
def main():
    carpeta = get_latest_folder(BASE_FOLDER)
    if not carpeta:
        return
    fecha = os.path.basename(carpeta)
    archivos = [f for f in os.listdir(carpeta) if f.lower().endswith(".xlsx")]
    if not archivos:
        print("❌ No hay archivos .xlsx en la carpeta.")
        return

    barrios, dfs = [], []
    for nombre in sorted(archivos):
        barrio = os.path.splitext(nombre)[0]
        path = os.path.join(carpeta, nombre)
        df = cargar_excel(path)
        barrios.append(barrio)
        dfs.append(df)

    generar_informe_global(dfs, barrios, fecha, carpeta)

if __name__ == "__main__":
    main()
