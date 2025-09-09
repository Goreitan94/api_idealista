# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image
import tempfile


# -----------------------------
# LÓGICA DE LOGIN (solo contraseña)
# -----------------------------
# En un entorno de producción, la contraseña NO debería estar aquí.
# Debería estar en Streamlit Secrets o en una variable de entorno.
PASSWORD = "Goreitan94" 

# Inicializar st.session_state para la autenticación
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Muestra el formulario de login si el usuario no está autenticado
if not st.session_state.authenticated:
    st.title("🔒 Iniciar Sesión en UrbenEye")
    with st.form("login_form"):
        st.info("Introduce la clave de acceso para continuar.")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            if password == PASSWORD:
                st.session_state.authenticated = True
                st.experimental_rerun()
            else:
                st.error("Contraseña incorrecta. Inténtalo de nuevo.")
    st.stop() # Detiene la ejecución del resto de la app si no se ha iniciado sesión


# -----------------------------
# RESTO DE TU APP (DESDE AQUÍ HACIA ABAJO)
# -----------------------------
st.set_page_config(layout="wide", page_title="Calculadora Inmobiliaria UrbenEye", page_icon="🏡", initial_sidebar_state="expanded")

# -----------------------------
# Configuración inicial
# -----------------------------
# Valores por defecto (reseteables)
DEFAULTS = {
    "roi": 25,
    "dias_balance": 200,
    "m2": 80,
    "precio_m2_reformado": 3000,
    "precio_m2_noreformado": 2500,
    "gastos_especiales": 0,
    "comision_venta_pct": 3,
    "broker_pct": 0.0,
    "porcentaje_financiado": 75,
    "interes_anual": 0.0,
    "precio_compra_estimado": 200000 
}

# -----------------------------
# Tema claro/oscuro (CSS)
# -----------------------------
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

def toggle_theme():
    st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'

if st.session_state.theme == 'dark':
    bg_color, text_color, header_color = '#0E1117', '#FAFAFA', '#FAFAFA'
    plotly_template = 'plotly_dark'
else:
    bg_color, text_color, header_color = '#FFFFFF', '#111827', '#0B5FFF'
    plotly_template = 'plotly_white'

st.markdown(f"""
<style>
    .reportview-container {{ background-color: {bg_color}; color: {text_color}; }}
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    h1, h2, h3, h4, h5, h6 {{ color: {header_color}; }}
    .stSidebar > div:first-child {{ background-color: {bg_color}; }}
    [data-testid="stMetricValue"] {{ color: {text_color} !important; }}
    [data-testid="stMetricLabel"] {{ color: {text_color} !important; }}
    .stMarkdown, .stText, .stCode, .stSelectbox label, .stNumberInput label {{ color: {text_color} !important; }}
    .stButton > button {{ cursor: pointer; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Utilidades financieras
# -----------------------------
def pmt(rate_annual, nper, pv):
    """Monthly payment (rate_annual expressed as decimal)."""
    if nper == 0:
        return 0
    if rate_annual == 0:
        return pv / nper
    rate_monthly = rate_annual / 12.0
    return (rate_monthly * pv) / (1 - (1 + rate_monthly) ** (-nper))

# -----------------------------
# Cálculos principales
# -----------------------------
def calcular_resultados(
    m2,
    precio_m2_reformado,
    precio_m2_noreformado,
    gastos_especiales,
    comision_venta_pct,
    broker_pct,
    porcentaje_financiado,
    interes_anual,
    dias_balance,
    roi_objetivo,
    precio_compra_fijo=None, # Parámetro opcional para los gráficos
    coste_reforma_fijo=None # Parámetro opcional para los gráficos
):
    """
    Calcula todos los escenarios (Sin reforma + 3 reformas) y devuelve un dict con resultados detallados.
    Si se pasa un precio de compra fijo, no se usa el ROI objetivo.
    """
    IVA = 0.21
    notaria = 800.0
    registro = 200.0
    gastos_fijos = notaria + registro + gastos_especiales

    tipos = {
        "Sin Reforma": 0,
        "Lavado de cara": 500,
        "Reforma integral barata": 750,
        "Reforma integral normal": 1000
    }

    precio_venta_reformado_total = precio_m2_reformado * m2
    precio_venta_noreformado_total = precio_m2_noreformado * m2

    resultados = {}

    # Variables auxiliares
    t = dias_balance / 365.0
    
    for nombre, coste_m2 in tipos.items():
        if coste_reforma_fijo is not None:
            coste_reforma_base = m2 * coste_reforma_fijo
        else:
            coste_reforma_base = m2 * coste_m2

        iva_reforma = coste_reforma_base * IVA
        coste_reforma_total = coste_reforma_base + iva_reforma

        if nombre == "Sin Reforma":
            pv_total = precio_venta_noreformado_total
        else:
            pv_total = precio_venta_reformado_total

        comision_venta = pv_total * (comision_venta_pct / 100.0) * (1 + IVA)
        pv_neto = pv_total - comision_venta
        
        # Broker factor (incluye IVA)
        broker_factor = (broker_pct / 100.0) * (1 + IVA)

        if precio_compra_fijo is not None:
            # Flujo para gráficos de valor: el precio de compra es fijo
            precio_compra = precio_compra_fijo
            broker_fee = precio_compra * broker_factor
            inversion_total = precio_compra + gastos_fijos + coste_reforma_total + broker_fee
        else:
            # Flujo normal: se calcula el precio de compra en base al ROI objetivo
            r_ann_obj = roi_objetivo / 100.0
            roi_abs_obj = r_ann_obj * t
            denom_inv = 1.0 + roi_abs_obj
            inv_total_obj = pv_neto / denom_inv if denom_inv > 0 else 0
            const_b = gastos_fijos + coste_reforma_total
            denom_pc = 1.0 + broker_factor
            precio_compra = max((inv_total_obj - const_b) / denom_pc, 0.0)
            
            broker_fee = precio_compra * broker_factor
            inversion_total = precio_compra + const_b + broker_fee


        ganancia_bruta = pv_neto - inversion_total

        # ROI Unleveraged (proyecto puro)
        roi_abs = ganancia_bruta / inversion_total if inversion_total > 0 else 0.0
        roi_anual_unlev = roi_abs / t if t > 0 else 0.0

        # Financiación / apalancamiento
        if porcentaje_financiado > 0:
            monto_financiado = precio_compra * (porcentaje_financiado / 100.0)
        else:
            monto_financiado = 0.0
        down_payment = inversion_total - monto_financiado if inversion_total > 0 else 0.0
        interes_total = monto_financiado * (interes_anual / 100.0) * t
        cuota_mensual = pmt(interes_anual / 100.0, 300, monto_financiado) if monto_financiado > 0 else 0.0
        pago_total_holding = cuota_mensual * (dias_balance / 30.0) if cuota_mensual > 0 else 0.0

        ganancia_neta_lev = ganancia_bruta - interes_total
        roi_abs_lev = ganancia_neta_lev / down_payment if down_payment > 0 else 0.0
        roi_anual_lev = roi_abs_lev / t if t > 0 else 0.0

        preferred = 0.08 * inversion_total

        distrib_inversor = 0.0
        distrib_management = 0.0
        if ganancia_neta_lev <= 0:
            distrib_inversor = max(0.0, ganancia_neta_lev)
            distrib_management = 0.0
        else:
            if ganancia_neta_lev <= preferred:
                distrib_inversor = ganancia_neta_lev
                distrib_management = 0.0
            else:
                excedente = ganancia_neta_lev - preferred
                distrib_inversor = preferred + 0.75 * excedente
                distrib_management = 0.25 * excedente

        viable = (roi_anual_unlev >= 0.20) if precio_compra_fijo is None else (roi_anual_lev >= 0.20)
        
        resultados[nombre] = {
            "PrecioVentaTotal": pv_total,
            "PrecioVentaNeto": pv_neto,
            "PrecioCompraMax": precio_compra,
            "BrokerFee": broker_fee,
            "GastosAdquisicionFijos": gastos_fijos,
            "CostoReformaBase": coste_reforma_base,
            "IVA_Reforma": iva_reforma,
            "CostoReformaTotal": coste_reforma_total,
            "InversionTotal": inversion_total,
            "DownPayment": down_payment,
            "MontoFinanciado": monto_financiado,
            "InteresTotalPeriodo": interes_total,
            "PagoMensual": cuota_mensual,
            "PagoTotalHolding": pago_total_holding,
            "GananciaBruta": ganancia_bruta,
            "GananciaNetaLeveraged": ganancia_neta_lev,
            "ROI_unleveraged_abs": roi_abs,
            "ROI_unleveraged_anual": roi_anual_unlev,
            "ROI_leveraged_abs": roi_abs_lev,
            "ROI_leveraged_anual": roi_anual_lev,
            "Preferred": preferred,
            "DistribInversor": distrib_inversor,
            "DistribManagement": distrib_management,
            "Viable": viable
        }

    return resultados


# -----------------------------
# Generadores de gráficos de valor (ROI vs. variables)
# -----------------------------
def generar_grafico_roi_vs_precio_venta(m2, pc_estimado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance, roi_objetivo, leveraged=False):
    precios = np.arange(1000, 5000 + 1, step=100)
    data = []
    roi_key = "ROI_leveraged_anual" if leveraged else "ROI_unleveraged_anual"
    titulo = "ROI Apalancado" if leveraged else "ROI Sin Apalancar"

    for p in precios:
        res = calcular_resultados(
            m2=m2, precio_m2_reformado=p, precio_m2_noreformado=precio_m2_noreformado,
            gastos_especiales=gastos_especiales, comision_venta_pct=comision_venta_pct,
            broker_pct=broker_pct, porcentaje_financiado=0 if not leveraged else 75,
            interes_anual=0 if not leveraged else 0, dias_balance=dias_balance,
            roi_objetivo=roi_objetivo, precio_compra_fijo=pc_estimado,
            coste_reforma_fijo=DEFAULTS["precio_m2_reformado"]-DEFAULTS["precio_m2_noreformado"]
        )
        roi_val = res["Lavado de cara"][roi_key]
        data.append((p, roi_val * 100))
    df = pd.DataFrame(data, columns=["Precio_m2", f"{titulo}_%"])
    
    fig = px.line(df, x="Precio_m2", y=f"{titulo}_%", title=f"{titulo} vs Precio de Venta €/m²", template=plotly_template)
    fig.add_hline(y=20, line_dash="dash", line_color="red", annotation_text="Viabilidad 20%", annotation_position="top right")
    fig.update_layout(xaxis_title="Precio de Venta €/m²", yaxis_title=f"{titulo} (%)")
    return fig


def generar_grafico_ganancia_vs_coste_reforma(m2, pc_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance, leveraged=False):
    costes = np.arange(0, 1500 + 1, 50)
    data = []
    ganancia_key = "GananciaNetaLeveraged" if leveraged else "GananciaBruta"
    titulo = "Ganancia Neta" if leveraged else "Ganancia Bruta"

    for cost_m2 in costes:
        res = calcular_resultados(
            m2=m2, precio_m2_reformado=precio_m2_reformado, precio_m2_noreformado=precio_m2_noreformado,
            gastos_especiales=gastos_especiales, comision_venta_pct=comision_venta_pct,
            broker_pct=broker_pct, porcentaje_financiado=0 if not leveraged else 75,
            interes_anual=0 if not leveraged else 0, dias_balance=dias_balance,
            roi_objetivo=0, precio_compra_fijo=pc_estimado, coste_reforma_fijo=cost_m2
        )
        ganancia_val = res["Lavado de cara"][ganancia_key]
        data.append((cost_m2, ganancia_val))
    df = pd.DataFrame(data, columns=["Coste_m2", f"{titulo}_€"])
    
    fig = px.line(df, x="Coste_m2", y=f"{titulo}_€", title=f"{titulo} vs Coste de Reforma €/m²", template=plotly_template)
    fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Punto de Equilibrio", annotation_position="bottom right")
    fig.update_layout(xaxis_title="Coste de Reforma €/m²", yaxis_title=f"{titulo} (€)")
    return fig

def generar_grafico_ganancia_vs_dias(m2, pc_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, interes_anual, leveraged=False):
    dias = np.arange(10, 365 + 1, 10)
    data = []
    ganancia_key = "GananciaNetaLeveraged" if leveraged else "GananciaBruta"
    titulo = "Ganancia Neta" if leveraged else "Ganancia Bruta"

    for d in dias:
        res = calcular_resultados(
            m2=m2, precio_m2_reformado=precio_m2_reformado, precio_m2_noreformado=precio_m2_noreformado,
            gastos_especiales=gastos_especiales, comision_venta_pct=comision_venta_pct,
            broker_pct=broker_pct, porcentaje_financiado=0 if not leveraged else 75,
            interes_anual=0 if not leveraged else interes_anual, dias_balance=d,
            roi_objetivo=0, precio_compra_fijo=pc_estimado,
            coste_reforma_fijo=DEFAULTS["precio_m2_reformado"]-DEFAULTS["precio_m2_noreformado"]
        )
        ganancia_val = res["Lavado de cara"][ganancia_key]
        data.append((d, ganancia_val))
    df = pd.DataFrame(data, columns=["Dias", f"{titulo}_€"])

    fig = px.line(df, x="Dias", y=f"{titulo}_€", title=f"{titulo} vs Días en el Mercado", template=plotly_template)
    fig.update_layout(xaxis_title="Días en el mercado", yaxis_title=f"{titulo} (€)")
    return fig

# -----------------------------
# Exportadores (Excel)
# -----------------------------
def exportar_excel(resultados):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        # summary
        rows = []
        for esc, data in resultados.items():
            row = {'Escenario': esc}
            row.update({
                'PrecioVentaTotal': data['PrecioVentaTotal'],
                'PrecioCompraMax': data['PrecioCompraMax'],
                'InversionTotal': data['InversionTotal'],
                'GananciaBruta': data['GananciaBruta'],
                'GananciaNetaLeveraged': data['GananciaNetaLeveraged'],
                'ROI_unleveraged_anual_%': data['ROI_unleveraged_anual'] * 100,
                'ROI_leveraged_anual_%': data['ROI_leveraged_anual'] * 100,
                'Viable': data['Viable']
            })
            rows.append(row)
        df_summary = pd.DataFrame(rows)
        df_summary.to_excel(writer, index=False, sheet_name='Resumen')

        # sheets por escenario
        for esc, data in resultados.items():
            df = pd.DataFrame(list(data.items()), columns=['Métrica', 'Valor'])
            df.to_excel(writer, index=False, sheet_name=esc[:31])  # sheet name <=31 chars
    out.seek(0)
    return out

# -----------------------------
# Interfaz - Inputs
# -----------------------------
with st.sidebar:
    st.header("Configuración Global")
    st.button(f"Cambiar a Tema {'Claro' if st.session_state.theme == 'dark' else 'Oscuro'}", on_click=toggle_theme)
    st.markdown("---")
    # Reset
    if st.button("🔄 Reset parámetros (valores por defecto)"):
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
    st.markdown("---")
    
    st.markdown("### Parámetros de mercado / propiedad")
    m2 = st.number_input("Metros cuadrados (m²)", value=st.session_state.get("m2", DEFAULTS["m2"]), step=1, key="m2")
    precio_m2_reformado = st.number_input("Precio venta €/m² (reformado)", value=st.session_state.get("precio_m2_reformado", DEFAULTS["precio_m2_reformado"]), step=50, key="precio_m2_reformado")
    precio_m2_noreformado = st.number_input("Precio venta €/m² (sin reformar)", value=st.session_state.get("precio_m2_noreformado", DEFAULTS["precio_m2_noreformado"]), step=50, key="precio_m2_noreformado")
    precio_compra_estimado = st.number_input("Precio de compra estimado (€)", value=st.session_state.get("precio_compra_estimado", DEFAULTS["precio_compra_estimado"]), step=1000, key="precio_compra_estimado")
    st.markdown("---")
    
    st.markdown("### ROI objetivo y días en balance")
    roi = st.number_input("ROI objetivo anual (%)", value=st.session_state.get("roi", DEFAULTS["roi"]), step=1, key="roi")
    roi_slider = st.slider("Mover ROI (%)", min_value=0, max_value=200, value=int(roi), step=1)
    dias_balance = st.number_input("Días en balance", value=st.session_state.get("dias_balance", DEFAULTS["dias_balance"]), step=10, key="dias_balance")
    st.markdown("---")

    st.markdown("### Costes y financiación")
    gastos_especiales = st.number_input("Gastos especiales (€)", value=st.session_state.get("gastos_especiales", DEFAULTS["gastos_especiales"]), step=50, key="gastos_especiales")
    comision_venta_pct = st.selectbox("Comisión de venta (%)", options=[1, 3], index=1 if DEFAULTS["comision_venta_pct"] == 3 else 0, key="comision_venta_pct")
    broker_pct = st.number_input("Broker fee (%)", value=st.session_state.get("broker_pct", DEFAULTS["broker_pct"]), step=0.5, key="broker_pct")
    porcentaje_financiado = st.number_input("Porcentaje financiado (%)", value=st.session_state.get("porcentaje_financiado", DEFAULTS["porcentaje_financiado"]), min_value=0, max_value=100, step=1, key="porcentaje_financiado")
    interes_anual = st.number_input("Interés anual (%)", value=st.session_state.get("interes_anual", DEFAULTS["interes_anual"]), step=0.25, key="interes_anual")

# -----------------------------
# Cálculo
# -----------------------------
resultados_base = calcular_resultados(
    m2=m2,
    precio_m2_reformado=precio_m2_reformado,
    precio_m2_noreformado=precio_m2_noreformado,
    gastos_especiales=gastos_especiales,
    comision_venta_pct=comision_venta_pct,
    broker_pct=broker_pct,
    porcentaje_financiado=porcentaje_financiado,
    interes_anual=interes_anual,
    dias_balance=dias_balance,
    roi_objetivo=roi_slider,
    precio_compra_fijo=None # Se usa el flujo de cálculo por ROI
)

# -----------------------------
# Presentación – KPIs Ejecutivos
# -----------------------------
st.title("🏡 UrbenEye — Calculadora de Oportunidades")
st.markdown("Resumen ejecutivo: compara rápidamente los 4 escenarios (sin reforma + 3 niveles de reforma).")

kpis_cols = st.columns(4)
ref = resultados_base["Lavado de cara"]
kpis_cols[0].metric("Precio Compra Máx (Lavado)", f"{ref['PrecioCompraMax']:,.0f} €")
kpis_cols[1].metric("ROI sin apalancar (Lavado)", f"{ref['ROI_unleveraged_anual']*100:.1f} %")
kpis_cols[2].metric("Ganancia Inversor (Lavado)", f"{ref['DistribInversor']:,.0f} €")
kpis_cols[3].metric("Ganancia Management (Lavado)", f"{ref['DistribManagement']:,.0f} €")

st.markdown("---")

# -----------------------------
# Tabla comparativa (con estilo)
# -----------------------------
st.subheader("📊 Comparativa de Escenarios")
df_comp = pd.DataFrame(resultados_base).T[[
    "PrecioCompraMax", "InversionTotal", "GananciaNetaLeveraged", "ROI_unleveraged_anual", "ROI_leveraged_anual", "Viable"
]]
df_comp = df_comp.rename(columns={
    "PrecioCompraMax": "PrecioCompraMax (€)",
    "InversionTotal": "InversiónTotal (€)",
    "GananciaNetaLeveraged": "GananciaNeta (€)",
    "ROI_unleveraged_anual": "ROI_unlev_anual (%)",
    "ROI_leveraged_anual": "ROI_lev_anual (%)",
    "Viable": "Viable"
})

df_comp["ROI_unlev_anual (%)"] = pd.to_numeric(df_comp["ROI_unlev_anual (%)"], errors='coerce').fillna(0) * 100
df_comp["ROI_unlev_anual (%)"] = df_comp["ROI_unlev_anual (%)"].round(1)

df_comp["ROI_lev_anual (%)"] = pd.to_numeric(df_comp["ROI_lev_anual (%)"], errors='coerce').fillna(0) * 100
df_comp["ROI_lev_anual (%)"] = df_comp["ROI_lev_anual (%)"].round(1)

df_comp["PrecioCompraMax (€)"] = pd.to_numeric(df_comp["PrecioCompraMax (€)"], errors='coerce').fillna(0).round(0).astype(int)
df_comp["InversiónTotal (€)"] = pd.to_numeric(df_comp["InversiónTotal (€)"], errors='coerce').fillna(0).round(0).astype(int)
df_comp["GananciaNeta (€)"] = pd.to_numeric(df_comp["GananciaNeta (€)"], errors='coerce').fillna(0).round(0).astype(int)

def style_viability(v):
    return "background-color: #2ecc71; color: white" if v else "background-color: #e74c3c; color: white"

st.dataframe(df_comp.style.applymap(style_viability, subset=["Viable"]))

st.markdown("---")

# -----------------------------
# Pestañas por escenario con detalle
# -----------------------------
tabs = st.tabs(list(resultados_base.keys()))
for tab_name, tab in zip(resultados_base.keys(), tabs):
    with tab:
        res = resultados_base[tab_name]
        st.subheader(f"Detalle: {tab_name}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Precio Venta Total", f"{res['PrecioVentaTotal']:,.0f} €")
        c2.metric("Precio Compra Máx", f"{res['PrecioCompraMax']:,.0f} €")
        c3.metric("Inversión Total", f"{res['InversionTotal']:,.0f} €")
        c4.metric("Viable", "✅" if res['Viable'] else "❌")

        st.markdown("#### Rentabilidades")
        r1, r2, r3 = st.columns(3)
        r1.metric("ROI unleveraged (anual)", f"{res['ROI_unleveraged_anual']*100:.2f} %")
        r2.metric("ROI leveraged (anual)", f"{res['ROI_leveraged_anual']*100:.2f} %")
        r3.metric("Preferred (8% inv.)", f"{res['Preferred']:,.0f} €")

        with st.expander("🔍 Desglose completo"):
            st.write(pd.Series(res).to_frame("Valor"))

            st.markdown("**Distribución de la inversión**")
            df_pie = pd.DataFrame({
                "Componente": ["Precio Compra", "Gastos Adquisicion", "Costo Reforma", "Broker Fee"],
                "Importe": [res["PrecioCompraMax"], res["GastosAdquisicionFijos"], res["CostoReformaTotal"], res["BrokerFee"]]
            })
            fig_pie = px.pie(df_pie, values='Importe', names='Componente', title=f"Desglose inversión — {tab_name}")
            fig_pie.update_traces(textinfo='percent+label')
            fig_pie.update_layout(template=plotly_template)
            st.plotly_chart(fig_pie, use_container_width=True)

            st.markdown("**Flujo de la financiación**")
            st.write({
                "Down Payment": f"{res['DownPayment']:,.0f} €",
                "Monto Financiado": f"{res['MontoFinanciado']:,.0f} €",
                "Intereses periodo": f"{res['InteresTotalPeriodo']:,.0f} €",
                "Cuota mensual (aprox.)": f"{res['PagoMensual']:,.0f} €",
                "PagoTotal periodo (aprox.)": f"{res['PagoTotalHolding']:,.0f} €"
            })

            st.markdown("**Distribución de beneficios**")
            st.write({
                "Ganancia Bruta (antes intereses)": f"{res['GananciaBruta']:,.0f} €",
                "Ganancia Neta (después intereses)": f"{res['GananciaNetaLeveraged']:,.0f} €",
                "Preferred (8%)": f"{res['Preferred']:,.0f} €",
                "A Inversor (total)": f"{res['DistribInversor']:,.0f} €",
                "A Management (total)": f"{res['DistribManagement']:,.0f} €"
            })

st.markdown("---")

# -----------------------------
# Nuevos gráficos de valor (ROI vs. variables)
# -----------------------------
st.subheader("Análisis de sensibilidad (sin apalancar)")
st.info("Estos gráficos se basan en un precio de compra fijo (el que has introducido) para mostrar cómo la rentabilidad varía con otras métricas clave.")

col_g1, col_g2 = st.columns(2)
with col_g1:
    fig_roi_pv = generar_grafico_roi_vs_precio_venta(m2, precio_compra_estimado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance, roi_slider)
    st.plotly_chart(fig_roi_pv, use_container_width=True)
with col_g2:
    fig_reforma_cost = generar_grafico_ganancia_vs_coste_reforma(m2, precio_compra_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance)
    st.plotly_chart(fig_reforma_cost, use_container_width=True)

fig_dias = generar_grafico_ganancia_vs_dias(m2, precio_compra_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, interes_anual)
st.plotly_chart(fig_dias, use_container_width=True)

# Sección de gráficos apalancados (opcional, en un expander)
with st.expander("Análisis de apalancamiento (para comparación)"):
    st.subheader("Análisis de apalancamiento")
    st.warning("Estos gráficos se basan en un precio de compra fijo (el que has introducido) y una financiación del 75% para mostrar el efecto del apalancamiento.")
    col_g3, col_g4 = st.columns(2)
    with col_g3:
        fig_roi_pv_lev = generar_grafico_roi_vs_precio_venta(m2, precio_compra_estimado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance, roi_slider, leveraged=True)
        st.plotly_chart(fig_roi_pv_lev, use_container_width=True)
    with col_g4:
        fig_reforma_cost_lev = generar_grafico_ganancia_vs_coste_reforma(m2, precio_compra_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, dias_balance, leveraged=True)
        st.plotly_chart(fig_reforma_cost_lev, use_container_width=True)
    fig_dias_lev = generar_grafico_ganancia_vs_dias(m2, precio_compra_estimado, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, interes_anual, leveraged=True)
    st.plotly_chart(fig_dias_lev, use_container_width=True)


st.markdown("---")
st.subheader("Exportar informe")
c_export = st.columns(2)

with c_export[0]:
    if st.button("Exportar a Excel"):
        excel_file = exportar_excel(resultados_base)
        st.download_button(
            label="Descargar Excel",
            data=excel_file,
            file_name="Informe_oportunidad.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with c_export[1]:
    st.button("Exportar a PDF")
    st.info("Para exportar, haz clic en el botón y luego usa la opción 'Imprimir' de tu navegador (Ctrl+P o Cmd+P) y selecciona 'Guardar como PDF' o 'Microsoft Print to PDF' como destino.")
