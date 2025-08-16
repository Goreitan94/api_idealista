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
        return f"€{x:,.0f}".replace(",", ".")  # separador millares estilo EU
    except:
        return ""

def fig_html(fig) -> str:
    # Devolvemos HTML del gráfico sin volver a incluir plotly.js
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
    if col in ("price", "price_per_m2"):
        fig.update_yaxes(title="Frecuencia")
        fig.update_xaxes(title=title.split("—")[-1].strip(), tickformat=",")
        fig.update_traces(hovertemplate=f"{title.split('—')[-1].strip()}: %{{x:,.0f}}<br>Frecuencia: %{{y}}<extra></extra>")
    elif col == "size":
        fig.update_xaxes(title="Tamaño (m²)", tickformat=",")
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
    # Línea de tendencia simple con numpy (sin statsmodels)
    clean = df[["size","price"]].dropna()
    if len(clean) >= 2:
        m, b = np.polyfit(clean["size"], clean["price"], 1)
        x_line = np.linspace(clean["size"].min(), clean["size"].max(), 50)
        y_line = m * x_line + b
        fig.add_trace(go.Scatter(x=x_line, y=y_line, mode="lines",
                                 name="Tendencia", line=dict(width=2)))
    fig.update_xaxes(title="Tamaño (m²)", tickformat=",")
    fig.update_yaxes(title="Precio (€)", tickformat=",")
    fig.update_traces(hovertemplate="m²: %{x:,.0f}<br>Precio: €%{y:,.0f}<extra></extra>")
    return fig_html(fig)

def barra_media(df, group_col, value_col, title, colors_map=None):
    if group_col not in df.columns or value_col not in df.columns:
        return ""
    g = df[[group_col, value_col]].dropna()
    if g.empty:
        return ""
    data = g.groupby(group_col)[value_col].mean().reset_index().sort_values(value_col, ascending=False)
    fig = px.bar(data, x=group_col, y=value_col, template=TEMPLATE, title=title,
                 color=group_col, color_discrete_map=colors_map or {}, text=value_col)
    fmt = "€%{y:,.0f}" if "€" in title or "€/m²" in title else "%{y:,.0f}"
    fig.update_traces(texttemplate=fmt, textposition='outside')
    fig.update_yaxes(tickformat=",")
    fig.update_layout(showlegend=False)
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
    # formato bonito
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
    fig.update_layout(template=TEMPLATE, title=title, margin=dict(l=0,r=0,t=40,b=0))
    return fig_html(fig)

# ==============================
# Informe (un solo HTML)
# ==============================
def generar_informe_global(all_dfs: list[pd.DataFrame], barrios: list[str], fecha: str, output_folder: str):
    # ---- HEAD + estilos + Plotly CDN ----
    parts = [f"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>Informe Interactivo — {fecha}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root {{
    --bg: #0b1020;
    --card: #121a33;
    --ink: #e6ecff;
    --muted: #a8b2d1;
    --accent: #6c9ef8;
    --accent2: #ff7a59;
  }}
  html, body {{ background: var(--bg); color: var(--ink); font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  .wrap {{ max-width: 1200px; margin: 40px auto; padding: 0 16px; }}
  .hero {{
    background: radial-gradient(1200px 400px at 20% -20%, rgba(108,158,248,0.25), transparent),
                radial-gradient(1000px 500px at 120% 20%, rgba(255,122,89,0.20), transparent);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 24px; padding: 28px 28px 18px; margin-bottom: 24px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.03);
  }}
  h1 {{ font-size: 32px; margin: 0 0 6px; letter-spacing: 0.3px; }}
  .sub {{ color: var(--muted); font-size: 14px; }}
  .toc {{ background: #0f1630; border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 14px 16px; margin: 18px 0 28px; }}
  .toc h3 {{ margin: 0 0 8px; font-size: 15px; color: var(--muted); }}
  .toc a {{ color: var(--ink); text-decoration: none; }}
  .toc a:hover {{ color: var(--accent); }}
  .section {{
    background: var(--card); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 18px; padding: 14px; margin: 14px 0 22px;
  }}
  .section > h2 {{
    font-size: 20px; margin: 8px 6px 10px; cursor: pointer; display: flex; align-items: center; gap: 8px;
  }}
  .pill {{ display:inline-block; font-size:12px; color:#081229; background:#cfe1ff; border-radius:999px; padding:2px 10px; margin-left:8px; }}
  .grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
  @media (min-width: 900px) {{
    .grid-2 {{ grid-template-columns: 1fr 1fr; }}
    .grid-3 {{ grid-template-columns: 1fr 1fr 1fr; }}
  }}
  .hint {{ color: var(--muted); font-size: 12px; margin: 8px 6px 0; }}
  details {{ margin-top: 8px; }}
  summary {{ list-style: none; }}
  summary::-webkit-details-marker {{ display:none; }}
  .anchor {{ scroll-margin-top: 90px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>📊 Informe Interactivo — {fecha}</h1>
    <div class="sub">Fuente: Idealista + OneDrive | Interactivo (zoom, hover, export)</div>
  </div>
"""]

    # ---- Unimos todo en un único dataframe para resumen global ----
    df_all = []
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty:
            continue
        tmp = df.copy()
        tmp["barrio"] = barrio
        df_all.append(tmp)
    if df_all:
        df_all = pd.concat(df_all, ignore_index=True)
    else:
        parts.append("<p>No hay datos.</p></div></body></html>")
        with open(os.path.join(output_folder, f"informe_interactivo_{fecha}.html"), "w", encoding="utf-8") as f:
            f.write("".join(parts))
        return

    # ---- TOC ----
    parts.append('<div class="toc"><h3>Navegación</h3><div style="display:flex;flex-wrap:wrap;gap:10px;">')
    parts.append(f'<a href="#resumen" class="pill">Resumen general</a>')
    for b in barrios:
        parts.append(f'<a href="#{slugify(b)}" class="pill">{b}</a>')
    parts.append('</div></div>')

    # ---- RESUMEN GLOBAL ----
    parts.append('<div id="resumen" class="section anchor"><h2>📌 Resumen general</h2>')
    # Media €/m² por barrio
    if "price_per_m2" in df_all.columns:
        m_ppm2 = (df_all[["barrio","price_per_m2"]]
                  .dropna().groupby("barrio").mean().reset_index()
                  .sort_values("price_per_m2", ascending=False))
        fig = px.bar(m_ppm2, x="barrio", y="price_per_m2", template=TEMPLATE,
                     title="€/m² medio por barrio", color="barrio",
                     color_discrete_sequence=PALETTE)
        fig.update_layout(showlegend=False)
        fig.update_yaxes(tickformat=",")
        parts.append(fig_html(fig))
    # Nº de anuncios por barrio
    cnt = df_all.groupby("barrio").size().reset_index(name="anuncios").sort_values("anuncios", ascending=False)
    fig = px.bar(cnt, x="barrio", y="anuncios", template=TEMPLATE, title="Nº de anuncios por barrio",
                 color="barrio", color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
    parts.append(fig_html(fig))
    parts.append('<div class="hint">Consejo: haz clic sobre los nombres en la leyenda (cuando exista) para filtrar; usa el icono de cámara para exportar</div></div>')

    # ---- SECCIONES POR BARRIO ----
    for barrio, df in zip(barrios, all_dfs):
        if df is None or df.empty:
            continue
        bid = slugify(barrio)
        parts.append(f'<div id="{bid}" class="section anchor">')
        parts.append(f'<h2>🏘️ {barrio} <span class="pill">{fecha}</span></h2>')

        # Grid 3: Histogramas
        parts.append('<div class="grid grid-3">')
        parts.append(histograma(df, "price", "Distribución — Precio (€)", PALETTE[0]))
        parts.append(histograma(df, "price_per_m2", "Distribución — €/m²", PALETTE[1]))
        parts.append(histograma(df, "size", "Distribución — Tamaño (m²)", PALETTE[2]))
        parts.append('</div>')

        # Grid 2: Scatter + Precio medio por nº habitaciones
        parts.append('<div class="grid grid-2">')
        parts.append(scatter_precio_size(df, PALETTE[3]))

        # Precio medio por nº habitaciones
        if "rooms" in df.columns and "price" in df.columns and df[["rooms","price"]].dropna().shape[0] > 0:
            pr = (df[["rooms","price"]].dropna()
                  .groupby("rooms")["price"].mean().reset_index()
                  .sort_values("rooms"))
            fig = px.bar(pr, x="rooms", y="price", template=TEMPLATE,
                         title="Precio medio por nº de habitaciones",
                         color="rooms", color_discrete_sequence=PALETTE, text="price")
            fig.update_traces(texttemplate="€%{y:,.0f}", textposition="outside")
            fig.update_yaxes(tickformat=",")
            fig.update_layout(showlegend=False)
            parts.append(fig_html(fig))
        else:
            parts.append("")

        parts.append('</div>')  # end grid-2

        # Grid 3: €/m² Exterior/Interior, Ascensor, Parking
        parts.append('<div class="grid grid-3">')
        # Exterior/Interior
        if "exterior_label" in df.columns and df["price_per_m2"].notna().any():
            fig = px.bar(
                df.dropna(subset=["price_per_m2"]),
                x="exterior_label", y="price_per_m2", template=TEMPLATE,
                title="€/m² — Exterior vs Interior",
                color="exterior_label",
                color_discrete_map={"Exterior": PALETTE[4], "Interior": PALETTE[5]}
            )
            fig.update_traces(texttemplate="€%{y:,.0f}", text="price_per_m2", textposition="outside")
            fig.update_yaxes(tickformat=",")
            fig.update_layout(showlegend=False)
            parts.append(fig_html(fig))
        else:
            parts.append("")

        # Ascensor
        if "lift_label" in df.columns and df["price_per_m2"].notna().any():
            fig = px.bar(
                df.dropna(subset=["price_per_m2"]),
                x="lift_label", y="price_per_m2", template=TEMPLATE,
                title="€/m² — Con y sin Ascensor",
                color="lift_label",
                color_discrete_map={"Con Ascensor": PALETTE[6], "Sin Ascensor": PALETTE[7]}
            )
            fig.update_traces(texttemplate="€%{y:,.0f}", text="price_per_m2", textposition="outside")
            fig.update_yaxes(tickformat=",")
            fig.update_layout(showlegend=False)
            parts.append(fig_html(fig))
        else:
            parts.append("")

        # Parking
        if "parking_label" in df.columns and df["price_per_m2"].notna().any():
            fig = px.bar(
                df.dropna(subset=["price_per_m2"]),
                x="parking_label", y="price_per_m2", template=TEMPLATE,
                title="€/m² — Con y sin Parking",
                color="parking_label",
                color_discrete_map={"Con Parking": PALETTE[8 % len(PALETTE)], "Sin Parking": PALETTE[9 % len(PALETTE)]}
            )
            fig.update_traces(texttemplate="€%{y:,.0f}", text="price_per_m2", textposition="outside")
            fig.update_yaxes(tickformat=",")
            fig.update_layout(showlegend=False)
            parts.append(fig_html(fig))
        else:
            parts.append("")
        parts.append('</div>')  # end grid-3

        # Tablas: 4 bloques
        cols_order = ['price', 'size', 'price_per_m2', 'rooms', 'exterior_label', 'lift_label', 'parking_label']
        parts.append('<div class="grid grid-2">')
        parts.append(tabla(df, "Top 10 — Más baratas (por precio)", "price", True, cols_order))
        parts.append(tabla(df, "Top 10 — Más caras (por precio)", "price", False, cols_order))
        parts.append('</div>')
        parts.append('<div class="grid grid-2">')
        parts.append(tabla(df, "Top 10 — Más baratas (por €/m²)", "price_per_m2", True, cols_order))
        parts.append(tabla(df, "Top 10 — Más caras (por €/m²)", "price_per_m2", False, cols_order))
        parts.append('</div>')

        # hint
        parts.append('<div class="hint">Pulsa el título para plegar/desplegar cada sección. Todos los gráficos son interactivos.</div>')
        parts.append('</div>')  # end section barrio

    # ---- Cierre ----
    parts.append("</div></body></html>")

    out_path = os.path.join(output_folder, f"informe_interactivo_{fecha}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"✅ Informe global guardado: {out_path}")

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
