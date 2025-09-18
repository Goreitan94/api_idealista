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
import json
from pathlib import Path

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

# ==============================
# Generador de Informe
# ==============================
def generar_informe_global(all_dfs: list[pd.DataFrame], barrios: list[str], fecha: str):
    print("DEBUG: Iniciando la generación del informe...")
    out_folder_pages = Path(os.environ.get("OUTPUT_FOLDER", "output_html"))
    out_folder_pages.mkdir(parents=True, exist_ok=True)
    (out_folder_pages / "datos_barrios").mkdir(parents=True, exist_ok=True)

    if not all_dfs:
        print("DEBUG: No hay datos para generar el informe. Terminando.")
        return

    df_all = pd.concat(all_dfs, ignore_index=True)

    # 1. Generar un JSON con los datos del mapa (todos los puntos)
    map_data = df_all[['latitude', 'longitude', 'price', 'size', 'url', 'barrio_slug']].to_dict('records')
    map_path = out_folder_pages / "mapa_data.json"
    map_path.write_text(json.dumps({{"properties": map_data}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ Archivo 'mapa_data.json' creado con éxito.")

    # 2. Generar un JSON individual para cada barrio
    for barrio_slug in list(df_all["barrio_slug"].unique()):
        df = df_all[df_all["barrio_slug"] == barrio_slug].copy()
        if df.empty:
            continue
        
        barrio_data = {{
            "nombre": barrio_slug.replace('-', ' ').title(),
            "resumen": df["price_per_m2"].mean() if not df.empty else 0,
            "top_caras": df.sort_values("price_per_m2", ascending=False).head(10).to_dict('records'),
            "top_baratas": df.sort_values("price_per_m2", ascending=True).head(10).to_dict('records'),
            "barrio_data": df[['price', 'size', 'rooms', 'exterior_label', 'lift_label', 'price_per_m2', 'url']].to_dict('records')
        }}
        
        json_path = out_folder_pages / "datos_barrios" / f"datos_barrio_{{barrio_slug}}.json"
        json_path.write_text(json.dumps(barrio_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Archivo '{{json_path}}' creado.")

    # 3. Generar el HTML estático con el nuevo JavaScript
    html_content = f"""
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8" />
    <title>UrbenEye — Informe Interactivo — {fecha}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        :root{{{{--bg:#0b1020;--card:#121a33;--ink:#e6ecff;--muted:#a8b2d1;--accent:#6c9ef8;}}}}
        html,body{{{{background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,'Open Sans','Helvetica Neue',sans-serif;line-height:1.5;}}}}
        .wrap{{{{max-width:1000px;margin:18px auto;padding:0 18px;}}}}
        a{{{{color:var(--accent);text-decoration:none;}}}}
        a:hover{{{{text-decoration:underline;}}}}
        h1,h2,h3{{{{font-family:'Segoe UI',-apple-system,system-ui,BlinkMacSystemFont,Roboto,Oxygen,Ubuntu,Cantarell,'Open Sans','Helvetica Neue',sans-serif;color:var(--ink);font-weight:700;line-height:1.2;}}}}
        .hero{{{{margin-bottom:30px;text-align:center;}}}}
        .hero h1{{{{font-size:32px;margin-bottom:8px;}}}}
        .sub{{{{color:var(--muted);font-size:14px;}}}}
        .toc{{{{padding:14px;background:var(--card);border:1px solid rgba(255,255,255,0.06);border-radius:18px;margin-bottom:22px;}}}}
        .toc h3{{{{font-size:16px;margin:0 0 10px;}}}}
        .toc a.pill{{{{color:#081229;background:#cfe1ff;border-radius:999px;padding:6px 12px;font-size:13px;text-decoration:none;display:inline-block;}}}}
        .toc a.pill:hover{{{{background:#9fc9ff;color:#03112a;text-decoration:none;}}}}
        .section{{{{background:var(--card);border:1px solid rgba(255,255,255,0.06);border-radius:18px;padding:14px;margin:14px 0 22px;}}}}
        .section > h2{{{{font-size:20px;margin:8px 6px 10px;}}}}
        .pill{{{{display:inline-block;font-size:12px;color:#081229;background:#cfe1ff;border-radius:999px;padding:2px 10px;margin-left:8px;}}}}
        .pill a{{{{color:#081229;text-decoration:none;}}}}
        .pill a:hover{{{{color:#004488;}}}}
        .grid{{{{display:grid;grid-template-columns:1fr;gap:14px;}}}}
        @media(min-width:900px){{{{--grid-2{{{{grid-template-columns:1fr 1fr;}}}} --grid-3{{{{grid-template-columns:1fr 1fr 1fr;}}}}}}}}
        .anchor{{{{scroll-margin-top:20px;}}}}
        table{{{{border-collapse: collapse;width: 100%;}}}}
        th, td{{{{text-align: left;padding: 8px;border-bottom: 1px solid #ddd;}}}}
        th{{{{background-color: #333;color: white;}}}}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="hero">
            <h1>📊 UrbenEye — Informe Interactivo — {fecha}</h1>
            <div class="sub">Fuente: Idealista API | Generado Automáticamente</div>
        </div>
        <div id="content">
            <div class="section anchor" id="mapa-general">
                <h2>📌 Mapa General</h2>
                <p style="text-align:center;">Haga clic en un punto para ver los detalles del barrio.</p>
                <div id="main-map" style="height: 600px;"></div>
            </div>
            <div id="barrio-data-container"></div>
        </div>
    </div>
    <script>
        const PALETTE = ['#6c9ef8', '#ff6b6b', '#ffd166', '#49a844', '#b388ff', '#06d6a0', '#ef476f', '#118ab2'];
        const TEMPLATE = 'plotly_dark';

        function fmt_eur(x) {{
            return '€' + parseFloat(x).toLocaleString('es-ES', {{maximumFractionDigits: 0}});
        }}
        
        function generarTablaHtml(data, title, cols_order) {{
            if (!data || data.length === 0) {{
                return '';
            }}
            const usable = data;

            const headerHtml = cols_order.map(c => `<th>${{c.replace('_', ' ').replace('Url', 'Anuncio').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}}</th>`).join('');
            
            const rowsHtml = usable.map(row => {{
                const cellsHtml = cols_order.map(c => {{
                    let val = row[c];
                    if (c === "price" || c === "size") {{
                        val = val.toLocaleString('es-ES');
                    }}
                    if (c === "price") {{
                        val = fmt_eur(val);
                    }} else if (c === "price_per_m2") {{
                        val = `${{fmt_eur(val)}}/m²`;
                    }} else if (c === "size") {{
                        val = `${{val}} m²`;
                    }} else if (c === "url") {{
                        val = `<a href='${{val}}' target='_blank'>Ver Anuncio</a>`;
                    }} else {{
                        val = String(val);
                    }}
                    return `<td>${{val}}</td>`;
                }}).join('');
                return `<tr>${{cellsHtml}}</tr>`;
            }}).join('');

            return `
                <div style="background:transparent; padding:0; margin-bottom:14px;">
                    <h2 style="font-size:18px; text-align:center; margin:8px 6px 10px;">${{title}}</h2>
                    <div style="max-height: 400px; overflow-y: auto;">
                    <table style="width:100%; border-collapse:collapse; text-align:center;">
                        <thead>
                            <tr style="background-color:#1a2445; color:white;">${{headerHtml}}</tr>
                        </thead>
                        <tbody style="background-color:#121a33; color:white;">
                            ${{rowsHtml}}
                        </tbody>
                    </table>
                    </div>
                </div>
            `;
        }}

        async function cargarDatosMapa() {{
            try {{
                const geojson = await fetch('/api_idealista/BARRIOS.geojson').then(r => r.json());
                const map_data_response = await fetch('/api_idealista/mapa_data.json').then(r => r.json());
                const all_properties = map_data_response.properties;

                const all_barrios_data = geojson.features.map(f => ({{...f.properties, 'color_del_mapa': '#404040'}}));
                
                const layout_mapa = {{
                    mapbox_style: 'carto-positron',
                    mapbox_zoom: 11,
                    mapbox_center: {{lat: 40.4168, lon: -3.7038}},
                    margin: {{t:0,b:0,l:0,r:0}},
                    showlegend: false,
                    height: 600
                }};
                
                const mapData = [
                    {{type: 'choroplethmapbox', geojson: geojson, locations: all_barrios_data.map(d => d.nombre), z: all_barrios_data.map(d => d.color_del_mapa === '#404040' ? 0 : 1), colorscale: [['0', '#404040'], ['1', '#6c9ef8']]}},
                    {{type: 'scattermapbox', lat: all_properties.map(d => d.latitude), lon: all_properties.map(d => d.longitude), mode: 'markers', marker: {{size: 8, color: '#ff6b6b', opacity: 0.7}}, hovertext: all_properties.map(d => '€' + d.price.toLocaleString() + ' | ' + d.size + ' m²'), hoverinfo: 'text', name: 'Inmuebles', customdata: all_properties.map(d => d.barrio_slug)}}
                ];
                
                const map = await Plotly.newPlot('main-map', mapData, layout_mapa);
                
                map.on('plotly_click', async function(data) {{
                    if (data.points.length > 0) {{
                        const barrioSlug = data.points[0].customdata;
                        if (barrioSlug) {{
                            document.getElementById('barrio-data-container').innerHTML = `
                                <div class="section anchor">
                                    <h2>Cargando datos de ${{barrioSlug.replace('-', ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}}...</h2>
                                </div>
                            `;
                            await cargarDatosBarrio(barrioSlug);
                        }}
                    }}
                }});

            }} catch (error) {{
                console.error('Error al cargar el mapa:', error);
                document.getElementById('content').innerHTML = `<p>Error al cargar el mapa. Intente recargar la página.</p>`;
            }}
        }}

        async function cargarDatosBarrio(barrioSlug) {{
            try {{
                const barrio_data = await fetch(`/api_idealista/datos_barrios/datos_barrio_${{barrioSlug}}.json`).then(r => r.json());
                const container = document.getElementById('barrio-data-container');
                
                const cols_order = ['price', 'size', 'price_per_m2', 'rooms', 'exterior_label', 'lift_label', 'url'];

                container.innerHTML = `
                    <div id="barrio-section" class="section anchor">
                        <h2>🏘️ ${{barrio_data.nombre}}</h2>
                        <div id="barrio-charts" class="grid grid-2">
                            <div id="chart-price-per-m2" style="height:350px;"></div>
                            <div id="chart-size-distribution" style="height:350px;"></div>
                        </div>
                        ${{generarTablaHtml(barrio_data.top_baratas, "Top 10 — Más baratas (por €/m²)", cols_order)}}
                        ${{generarTablaHtml(barrio_data.top_caras, "Top 10 — Más caras (por €/m²)", cols_order)}}
                    </div>
                `;
                
                // Gráfico de distribución de precios por m2
                const trace_ppm2 = {{
                    x: barrio_data.barrio_data.map(d => d.price_per_m2),
                    type: 'histogram',
                    marker: {{color: '#6c9ef8'}}
                }};
                const layout_ppm2 = {{
                    title: 'Distribución €/m²',
                    xaxis: {{title: '€/m²'}},
                    yaxis: {{title: 'Frecuencia'}},
                    template: TEMPLATE
                }};
                Plotly.newPlot('chart-price-per-m2', [trace_ppm2], layout_ppm2);

                // Gráfico de distribución de tamaño
                const trace_size = {{
                    x: barrio_data.barrio_data.map(d => d.size),
                    type: 'histogram',
                    marker: {{color: '#ff6b6b'}}
                }};
                const layout_size = {{
                    title: 'Distribución de tamaños',
                    xaxis: {{title: 'Tamaño (m²)'}},
                    yaxis: {{title: 'Frecuencia'}},
                    template: TEMPLATE
                }};
                Plotly.newPlot('chart-size-distribution', [trace_size], layout_size);

            }} catch (error) {{
                console.error('Error al cargar los datos del barrio:', error);
                document.getElementById('barrio-data-container').innerHTML = `<p>Error al cargar los datos del barrio. Intente recargar la página.</p>`;
            }}
        }}

        cargarDatosMapa();

    </script>
</body>
</html>
"""
    
    out_path_pages = out_folder_pages / "index.html"
    out_path_pages.write_text(html_content, encoding="utf-8")
    print(f"DEBUG: Archivo 'index.html' guardado en la ruta: {out_path_pages}")
    print(f"✅ Informe final (HTML) guardado en '{out_path_pages}'.")
    
    return "Informe y datos listos."

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
        
        out_folder_pages = Path(os.environ.get("OUTPUT_FOLDER", "output_html"))
        out_folder_pages.mkdir(parents=True, exist_ok=True)
        geojson_path = out_folder_pages / "BARRIOS.geojson"
        
        geojson_gdf.to_file(geojson_path, driver="GeoJSON")
        print(f"DEBUG: Archivo 'BARRIOS.geojson' guardado en la ruta: {geojson_path}")
        print("✅ Archivo GeoJSON de barrios de Madrid guardado para despliegue.")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado en el main: {e}")
        return

    try:
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
                
                df_limpio = pd.DataFrame()
                
                df_limpio['price'] = df['price']
                df_limpio['size'] = df['size']
                df_limpio['rooms'] = df['rooms']
                df_limpio['exterior'] = df['exterior']
                df_limpio['hasLift'] = df['hasLift']
                df_limpio['latitude'] = df['latitude']
                df_limpio['longitude'] = df['longitude']
                df_limpio['url'] = df['url']
                
                if 'size' in df_limpio.columns: df_limpio = df_limpio[df_limpio['size'] > 0].copy()
                if 'price' in df_limpio.columns: df_limpio = df_limpio[df_limpio['price'] > 0].copy()
                
                df_limpio['price_per_m2'] = df_limpio['price'] / df_limpio['size'].replace(0, np.nan)
                
                if 'exterior' in df_limpio.columns:
                    df_limpio['exterior_label'] = df_limpio['exterior'].apply(lambda x: 'Exterior' if x else 'Interior')
                if 'hasLift' in df_limpio.columns:
                    df_limpio['lift_label'] = df_limpio['hasLift'].apply(lambda x: 'Con Ascensor' if x else 'Sin Ascensor')
                
                df_limpio['barrio'] = barrio_nombre_original
                df_limpio['barrio_slug'] = barrio_slug
                
                barrios.append(barrio_nombre_original)
                dfs.append(df_limpio)
            except Exception as e:
                print(f"⚠️ Error procesando {a['name']}: {e}")

        if not dfs:
            print("❌ No se pudieron procesar los datos.")
            return

        print("\n📊 Generando informe HTML y JSON de datos...")
        generar_informe_global(dfs, barrios, fecha)
        print(f"✅ Proceso completado. Los archivos 'index.html', 'mapa_data.json' y 'BARRIOS.geojson' están listos para ser subidos, junto con las carpetas de datos de cada barrio.")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado en el main: {e}")

if __name__ == "__main__":
    main()
