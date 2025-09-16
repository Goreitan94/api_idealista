import os
import base64
import requests
import pandas as pd
from datetime import datetime
from io import BytesIO
from fuzzywuzzy import process
import urllib.parse
import random


# --- OUTPUT (para que Actions lo publique) ---
OUTPUT_FOLDER = os.environ.get("OUTPUT_FOLDER", "output_html")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------------------------------------------------------------------
# Usar variables de entorno en lugar de credenciales en el código
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
IDEALISTA_API_KEY = os.getenv("IDEALISTA_API_KEY")
IDEALISTA_SECRET = os.getenv("IDEALISTA_SECRET")

barrios = {
    "Palomeras sureste": "40.387095,-3.639793",
    "Nueva Numancia": "40.397566,-3.661992",
    "Moscardo": "40.390137,-3.706201",
    "San Fermin": "40.371046,-3.690084",
    "Orcasur": "40.367687,-3.700491",
    "Orcasitas": "40.370112,-3.715266",
    "Almendrales": "40.385761,-3.703806",
    "Comillas": "40.393867,-3.714791",
    "Opanel": "40.389528,-3.722737",
    "Abrantes": "40.376878,-3.733493",
    "San Isidro": "40.395360,-3.732453",
    "Puerta del Angel": "40.408647,-3.732017",
    "Bellas Vistas": "40.452556,-3.708115",
    "Berrugete": "40.460870,-3.705047",
    "Valdecederas": "40.466510,-3.701099",
    "Apstol Santiago": "40.476923,-3.660153",
    "Pinar del rey": "40.471138,-3.650982",
    "Villaverde": "40.348116,-3.699342",
    "Carabanchel": "40.385854,-3.750116",
    "San Blas": "40.435440,-3.631840",
    "Hortaleza": "40.467226,-3.650239",
    "Tetuan": "40.463301,-3.701233",
    "Getafe": "40.310179,-3.731004",
    "Pacifico": "40.405677,-3.673614",
    "Mostoles": "40.319641,-3.864797",
    "Alcorcon": "40.344370,-3.825567",
    "Adelfas": "40.400371,-3.673239",
    "Buenavista": "40.368199,-3.749999",
    "Puerta Bonita": "40.378677,-3.742062",
    "Chueca": "40.422712,-3.699568",
    "Arguelles": "40.429129,-3.718449",
    "Ibiza": "40.418772,-3.674032",
    "Goya": "40.424364,-3.672750",
    "Nino Jesus": "40.411190,-3.672553",
    "Fuente del berro": "40.424889,-3.664272",
    "Guindalera": "40.437122,-3.667279",
    "Cuatro Caminos": "40.450129,-3.698571",
    "Palacio":"40.414233, -3.711324",
    "Universidad":"40.426962, -3.706459",
    "Chopera":"40.396528, -3.697576",
    "Ciudad Jardin":"40.448814, -3.671915",
    "Prosperidad":"40.443221, -3.670212",
    "Rios Rosas":"40.442226, -3.697691",
    "Pilar":"40.477533, -3.708502",
    "Entrevias":"40.376578, -3.668765",
    "San Diego":"40.390638, -3.668534",
    "Palomeras Bajas":"40.386240, -3.658605",
    "Portazgo":"40.390683, -3.648258",
    "Numancia":"40.399027, -3.659753",
    "Pavones":"40.399350, -3.632046",
    "Ventas":"40.425611, -3.652941",
    "Pinar del Rey":"40.472659, -3.647214",
    "Apostol Santiago":"40.476311, -3.660456",
    
}

# ------------------------------------------------------------------------------
FILE_PATH_RAW = "/Idealista API (Datos)/benchmark_precios_act.xlsx"
FILE_PATH = urllib.parse.quote(FILE_PATH_RAW, safe="/:")
BASE_FOLDER = "/Idealista API (Datos)/Datos"

# ------------------------------------------------------------------------------
def get_onedrive_token():
    print("🔑 Solicitando token de OneDrive...")
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
        print("✅ Token OneDrive obtenido")
        return token_data["access_token"]
    else:
        print("❌ No se pudo obtener token OneDrive:", token_data)
        return None

# ------------------------------------------------------------------------------
def download_benchmark_file(access_token):
    print("📥 Descargando archivo de benchmark desde OneDrive...")
    url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{FILE_PATH}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("✅ Archivo benchmark descargado")
        return pd.read_excel(BytesIO(response.content))
    else:
        print("❌ Error al descargar archivo benchmark:", response.text)
        return None

# ------------------------------------------------------------------------------
def get_idealista_token():
    credentials = f"{IDEALISTA_API_KEY}:{IDEALISTA_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "read"}
    response = requests.post("https://api.idealista.com/oauth/token", headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print("❌ Error obteniendo token Idealista:", response.text)
        return None

# ------------------------------------------------------------------------------
def search_barrio(barrio, benchmark_df):
    print(f"\n🔍 Buscando propiedades en: {barrio}")
    coords = barrios[barrio]
    token = get_idealista_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "operation": "sale",
        "propertyType": "homes",
        "center": coords,
        "distance": "600",
        "sort": "desc",
        "maxItems": "50",
        "language": "es",
        "numPage": 1
    }

    response = requests.post("https://api.idealista.com/3.5/es/search", headers=headers, data=data)
    if response.status_code != 200:
        print(f"❌ Error en búsqueda de {barrio}:", response.text)
        return None

    anuncios = response.json().get("elementList", [])
    print(f"📦 Resultados: {len(anuncios)}")
    if not anuncios:
        return None

    benchmark_df.columns = benchmark_df.columns.str.strip()
    benchmark_mapping = {str(row['barrio']).strip().lower(): row['Compra'] for _, row in benchmark_df.iterrows()}
    data_cleaned = []

    for a in anuncios:
        a['barrio'] = barrio
        barrio_anuncio = str(a.get("neighborhood") or "").strip().lower()
        if barrio_anuncio:
            result = process.extractOne(barrio_anuncio, benchmark_mapping.keys(), score_cutoff=80)
            match = result[0] if result else None
        else:
            match = None
        compra_ref = benchmark_mapping.get(match) if match else None
        a['Compra'] = compra_ref
        a['Diferencia %'] = (a['price'] - compra_ref) / compra_ref * 100 if compra_ref else None
        data_cleaned.append(a)

    df = pd.DataFrame(data_cleaned).sort_values(by="Diferencia %", ascending=True)
    return df

# ------------------------------------------------------------------------------
def upload_to_onedrive(df, barrio, access_token, fecha_str):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{barrio}_{timestamp}.xlsx"
    save_path = f"{BASE_FOLDER}/{fecha_str}/{file_name}"

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    upload_url = f"https://graph.microsoft.com/v1.0/users/eitang@urbeneye.com/drive/root:{save_path}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.put(upload_url, headers=headers, data=output.read())
    if response.status_code in [200, 201]:
        print(f"✅ Archivo subido: {file_name}")
    else:
        print("❌ Error al subir archivo:", response.text)

# ------------------------------------------------------------------------------
def main():
    print("🚀 Ejecutando script Idealista")
    access_token = get_onedrive_token()
    if not access_token:
        return

    benchmark_df = download_benchmark_file(access_token)
    if benchmark_df is None:
        return

    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    # ⚡ Solo 1 barrio para pruebas
    seleccionados = random.sample(list(barrios.keys()), 20)
    print(f"🏘️ Barrios seleccionados: {seleccionados}")

    for barrio in seleccionados:
        df = search_barrio(barrio, benchmark_df)
        if df is not None and not df.empty:
            upload_to_onedrive(df, barrio, access_token, fecha_hoy)

    print(f"\n✅ Proceso finalizado. Archivos en carpeta: {fecha_hoy}")

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
