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

BASE_FOLDER = "/Idealista API (Datos)/Datos" # Carpeta raíz en OneDrive
TEMPLATE = "plotly_dark" # Cambiado a oscuro para coincidir con tu CSS
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
    # Se usa 'full_html=False' para incrustar, y se desactiva el logo y botones no deseados
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "modeBarButtonsToRemove": ["select", "lasso2d"]})

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

def tabla(df, title, sort_col, ascending, cols_order):
    usable = df.copy().sort_values(sort_col, ascending=ascending).head(10)
    # Aseguramos que 'url' esté al final si existe
    if 'url' in df.columns and 'url' not in cols_order:
        cols_order.append('url')

    usable = usable[[c for c in cols_order if c in usable.columns]]
    if usable.empty: return ""

    header = [c.replace("_"," ").title() for c in usable.columns]
    if 'Url' in header:
        header[header.index('Url')] = "Anuncio"

    cells_values = []
    for c in usable.columns:
        vals = usable[c].copy()
        if c == "price":
            vals = vals.apply(fmt_eur)
        elif c == "price_per_m2":
            vals = vals.apply(lambda v: f"{fmt_eur(v)}/m²")
        elif c == "size":
            vals = vals.apply(lambda v: f"{int(v):,} m²".replace(",", "."))
        elif c == 'url':
            # Genera un HTML con el enlace para la celda
            # Nota: go.Table puede no renderizar HTML complejo, pero funciona para enlaces simples.
            vals = [f'<a href="{url}" target="_blank">Ver Anuncio</a>' for url in vals]
        cells_values.append(vals.tolist())

    fig = go.Figure(data=[go.Table(
        header=dict(values=header, fill_color="#1a2445", align="center", font=dict(color='white')),
        cells=dict(values=cells_values, align="center", fill_color= '#121a33', font=dict(color='white'))
    )])
    fig.update_layout(template=TEMPLATE, title=title, margin=dict(l=10,r=10,t=40,b=10))
    return fig_html(fig)

# ==============================
# Generador de Informe
# ==============================
def generar_informe_global(all_dfs: list[pd.DataFrame], barrios: list[str], fecha: str):
    parts = [f"""
<!doctype html><html lang="es"><head><meta charset="utf-8" /><title>Informe Interactivo — {fecha}</title><meta name="viewport" content="width=device-width, initial-scale=1" /><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script><style>:root{{--bg:#0b1020;--card:#121a33;--ink:#e6ecff;--muted:#a8b2d1;--accent:#6c9ef8;}}html,body{{background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}} .wrap{{max-width:1200px;margin:40px auto;padding:0 16px;}} .hero{{background:radial-gradient(1200px 400px at 20% -20%,rgba(108,158,248,0.25),transparent),radial-gradient(1000px 500px at 120% 20%,rgba(255,122,89,0.20),transparent);border:1px solid rgba(255,255,255,0.06);border-radius:24px;padding:28px 28px 18px;margin-bottom:24px;box-shadow:0 20px 60px rgba(0,0,0,0.35),inset 0 1px 0 rgba(255,255,255,0.03);}} h1{{font-size:32px;margin:0 0 6px;}} .sub{{color:var(--muted);font-size:14px;}} .toc{{background:#0f1630;border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;margin:18px 0 28px;}} .toc h3{{margin:0 0 8px;font-size:15px;color:var(--muted);}} .toc a{{color:var(--ink);text-decoration:none;}} .toc a:hover{{color:var(--accent);}} .section{{background:var(--card);border:1px solid rgba(255,255,255,0.06);border-radius:18px;padding:14px;margin:14px 0 22px;}} .section > h2{{font-size:20px;margin:8px 6px 10px;}} .pill{{display:inline-block;font-size:12px;color:#081229;background:#cfe1ff;border-radius:999px;padding:2px 10px;margin-left:8px;}} .pill a{{color:#081229;text-decoration:none;}} .pill a:hover{{color:#004488;}} .grid{{display:grid;grid-template-columns:1fr;gap:14px;}} @media(min-width:900px){{.grid-2{{grid-template-columns:1fr 1fr;}} .grid-3{{grid-template-columns:1fr 1fr 1fr;}}}} .anchor{{scroll-margin-top:20px;}}</style></head><body><div class="wrap"><div class="hero"><h1>📊 Informe Interactivo — {fecha}</h1><div class="sub">Fuente: Idealista API | Generado Automáticamente</div></div>
"""]
    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty: continue
        tmp = df.copy()
        tmp["barrio"] = re.sub(r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$', '', barrio)
        df_all.append(tmp)
    if not df_all:
        parts.append("<p>No hay datos.</p></div></body></html>")
        return "".join(parts)
    df_all = pd.concat(df_all, ignore_index=True)
    barrios_unicos = df_all["barrio"].unique().tolist()
    
    parts.append('<div class="toc"><h3>Navegación</h3><div style="display:flex;flex-wrap:wrap;gap:10px;"><a href="#resumen" class="pill">Resumen general</a>')
    for b in barrios_unicos: parts.append(f'<a href="#{slugify(b)}" class="pill">{b}</a>')
    parts.append('</div></div>')
    
    parts.append('<div id="resumen" class="section anchor"><h2>📌 Resumen general</h2>')
    m_ppm2 = df_all.groupby("barrio")["price_per_m2"].mean().sort_values(ascending=False).reset_index()
    fig_resumen1 = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE, title="€/m² medio por barrio", color="barrio")
    parts.append(fig_html(fig_resumen1))
    parts.append('</div>')

    for i, barrio_nombre in enumerate(barrios_unicos):
        df = df_all[df_all["barrio"] == barrio_nombre]
        if df.empty: continue
        bid = slugify(barrio_nombre)
        color = PALETTE[i % len(PALETTE)]
        parts.append(f'<div id="{bid}" class="section anchor"><h2>🏘️ {barrio_nombre}</h2><div class="grid grid-3">')
        parts.append(histograma(df, "price", "Distribución de Precio (€)", color))
        parts.append(histograma(df, "price_per_m2", "Distribución de €/m²", color))
        parts.append(histograma(df, "size", "Distribución de Tamaño (m²)", color))
        parts.append('</div><div class="grid grid-2">')
        parts.append(scatter_precio_size(df, color))
        parts.append(scatter_price_size_trend(df, "€/m² vs Tamaño: Tendencia no lineal", color))
        parts.append(bar_chart_features(df, "€/m² Medio: Exterior vs Interior / Con vs Sin Ascensor", color))
        parts.append(bar_chart_lift_impact(df, "€/m² Medio: Con vs Sin Ascensor", color))
        parts.append('</div><div class="grid grid-2">')
        cols_order = ['price', 'size', 'price_per_m2', 'rooms', 'exterior_label', 'lift_label', 'url']
        parts.append(tabla(df, "Top 10 — Más baratas (por €/m²)", "price_per_m2", True, cols_order))
        parts.append(tabla(df, "Top 10 — Más caras (por €/m²)", "price_per_m2", False, cols_order))
        parts.append('</div></div>')
        
    parts.append("</div></body></html>")
    return "".join(parts)

# ==============================
# Main
# ==============================
def main():
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
        barrio_nombre = os.path.splitext(a["name"])[0]
        file_path = f"{carpeta_path}/{a['name']}"
        try:
            print(f"📥 Descargando y procesando: {a['name']}")
            df = download_excel(file_path, token)
            # Aplicar la limpieza avanzada de tu script local
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
    full_html = generar_informe_global(dfs, barrios, fecha)

    # Guardado para GitHub Pages
    out_folder_pages = os.environ.get("OUTPUT_FOLDER", "output_html")
    os.makedirs(out_folder_pages, exist_ok=True)
    # ¡Importante! El archivo debe llamarse index.html
    out_path_pages = os.path.join(out_folder_pages, "index.html")
    with open(out_path_pages, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ Informe final guardado en '{out_path_pages}' para su despliegue.")

if __name__ == "__main__":
    main()
