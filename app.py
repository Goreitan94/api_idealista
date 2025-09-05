import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np


password = st.text_input("Introduce la contraseña", type="password")
if password != "Eitangor94":
    st.error("Acceso denegado ❌")
    st.stop()

# -----------------------------
# Interfaz Streamlit - Configuración Inicial
# -----------------------------
st.set_page_config(layout="wide", page_title="Calculadora Inmobiliaria UrbenEye", page_icon="🏡", initial_sidebar_state="expanded")

# Estado inicial del tema (claro por defecto)
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

def toggle_theme():
    st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'

if st.session_state.theme == 'dark':
    bg_color, text_color, header_color = '#0E1117', '#FAFAFA', '#FAFAFA'
else:
    bg_color, text_color, header_color = '#FFFFFF', '#31333F', '#1A73E8'

st.markdown(f"""
<style>
    .reportview-container {{ background-color: {bg_color}; color: {text_color}; }}
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    h1, h2, h3, h4, h5, h6 {{ color: {header_color}; }}
    .stSidebar > div:first-child {{ background-color: {bg_color}; }}
    [data-testid="stMetricValue"] {{ color: {text_color} !important; }}
    [data-testid="stMetricLabel"] {{ color: {text_color} !important; }}
    .stMarkdown, .stText, .stCode, .stSelectbox label, .stNumberInput label {{ color: {text_color} !important; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Funciones auxiliares de cálculo
# -----------------------------
def pmt(rate, nper, pv):
    """Calculates the monthly payment for a loan."""
    if rate == 0:
        return pv / nper
    rate_monthly = rate / 12
    return (rate_monthly * pv) / (1 - (1 + rate_monthly)**-nper)

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
    custom_reforma_coste_m2=None # Nuevo parámetro para el gráfico de equilibrio
):
    resultados_dict = {}
    tipos_reforma = ["Lavado de cara", "Reforma integral barata", "Reforma integral normal"]
    
    # Precio de venta base y sin reforma
    precio_venta_reformado = precio_m2_reformado * m2
    comision_venta_reformado = precio_venta_reformado * (comision_venta_pct / 100) * 1.21

    precio_venta_noreformado = precio_m2_noreformado * m2
    comision_venta_noreformado = precio_venta_noreformado * (comision_venta_pct / 100) * 1.21

    # Gastos fijos
    notaria = 800
    registro = 200
    gastos_extra = gastos_especiales
    gastos_adquisicion_fijos = notaria + registro + gastos_extra

    # Escenario Sin Reforma
    coste_reforma_noref_base = 0
    iva_reforma_noref = 0
    coste_reforma_noref_total = 0 # Incluye IVA
    pv_neto_noref = precio_venta_noreformado - comision_venta_noreformado
    
    # Ecuación para precio de compra
    def precio_compra_objetivo(roi_obj, coste_reforma_total, pv_neto):
        t = dias_balance / 365
        a = (1 + broker_pct/100*1.21)
        b = gastos_adquisicion_fijos + coste_reforma_total
        num = pv_neto - b - roi_obj/100*t*b
        den = roi_obj/100*t*a + a
        return max(num / den, 0)
    
    precio_compra_max_noref = precio_compra_objetivo(roi_objetivo, coste_reforma_noref_total, pv_neto_noref)
    
    broker_fee_noref = precio_compra_max_noref * (broker_pct/100) * 1.21
    inversion_total_noref = precio_compra_max_noref + gastos_adquisicion_fijos + coste_reforma_noref_total + broker_fee_noref
    ganancia_bruta_noref = pv_neto_noref - inversion_total_noref
    roi_absoluto_noref = ganancia_bruta_noref / inversion_total_noref if inversion_total_noref > 0 else 0
    roi_anualizado_noref = roi_absoluto_noref / (dias_balance/365) if dias_balance > 0 else 0
    
    # Cálculos apalancados y beneficios
    if porcentaje_financiado > 0:
        monto_financiado_noref = precio_compra_max_noref * (porcentaje_financiado / 100)
        down_payment_noref = inversion_total_noref - monto_financiado_noref
        pago_mensual_noref = pmt(interes_anual/100, 300, monto_financiado_noref)
        interes_total_noref = monto_financiado_noref * (interes_anual/100) * (dias_balance/365)
        ganancia_neta_lev_noref = ganancia_bruta_noref - interes_total_noref
        roi_anualizado_lev_noref = (ganancia_neta_lev_noref / down_payment_noref) / (dias_balance/365) if down_payment_noref > 0 and dias_balance > 0 else 0
        pago_total_noref = pago_mensual_noref * (dias_balance / 30) if dias_balance > 0 else 0
    else:
        monto_financiado_noref = 0
        down_payment_noref = inversion_total_noref
        ganancia_neta_lev_noref = ganancia_bruta_noref
        roi_anualizado_lev_noref = roi_anualizado_noref
        pago_mensual_noref = 0
        pago_total_noref = 0

    preferred_noref = 0.08 * down_payment_noref
    distrib_inv_noref, distrib_mgmt_noref = (0, 0)
    if ganancia_neta_lev_noref > 0:
        if ganancia_neta_lev_noref <= preferred_noref:
            distrib_inv_noref = ganancia_neta_lev_noref
        else:
            excedente = ganancia_neta_lev_noref - preferred_noref
            distrib_inv_noref = preferred_noref + 0.75 * excedente
            distrib_mgmt_noref = 0.25 * excedente

    resultados_dict["Sin Reforma"] = {
        "PrecioVentaTotal": precio_venta_noreformado,
        "PrecioCompraMax": precio_compra_max_noref,
        "InversionTotal": inversion_total_noref,
        "MontoFinanciado": monto_financiado_noref, # Añadido
        "DownPayment": down_payment_noref,
        "GastosAdquisicionFijos": gastos_adquisicion_fijos,
        "CostoReformaTotal": coste_reforma_noref_total,
        "BrokerFee": broker_fee_noref,
        "GananciaBruta": ganancia_bruta_noref,
        "GananciaNetaLeveraged": ganancia_neta_lev_noref,
        "ROI_anual": roi_anualizado_noref,
        "ROI_anual_lev": roi_anualizado_lev_noref,
        "DistribInversor": distrib_inv_noref,
        "DistribManagement": distrib_mgmt_noref,
        "Viable": roi_anualizado_lev_noref >= 0.20 if porcentaje_financiado > 0 else roi_anualizado_noref >= 0.20,
        "PagoMensual": pago_mensual_noref,
        "PagoTotal": pago_total_noref,
        "CostoReformaBase": coste_reforma_noref_base,
        "IVA": iva_reforma_noref
    }

    # Escenarios con Reforma
    for tipo_reforma in tipos_reforma:
        if custom_reforma_coste_m2 is not None:
            coste_reforma_base = m2 * custom_reforma_coste_m2
        elif tipo_reforma == "Lavado de cara": coste_reforma_base = m2 * 500
        elif tipo_reforma == "Reforma integral barata": coste_reforma_base = m2 * 750
        else: coste_reforma_base = m2 * 1000
        
        iva_reforma = coste_reforma_base * 0.21
        coste_reforma_total = coste_reforma_base + iva_reforma
        
        pv_neto = precio_venta_reformado - comision_venta_reformado
        precio_compra_max = precio_compra_objetivo(roi_objetivo, coste_reforma_total, pv_neto)
        
        broker_fee = precio_compra_max * (broker_pct/100) * 1.21
        inversion_total = precio_compra_max + gastos_adquisicion_fijos + coste_reforma_total + broker_fee
        ganancia_bruta = pv_neto - inversion_total
        roi_absoluto = ganancia_bruta / inversion_total if inversion_total > 0 else 0
        roi_anualizado = roi_absoluto / (dias_balance/365) if dias_balance > 0 else 0
        
        if porcentaje_financiado > 0:
            monto_financiado = precio_compra_max * (porcentaje_financiado / 100)
            down_payment = inversion_total - monto_financiado
            pago_mensual = pmt(interes_anual/100, 300, monto_financiado)
            interes_total = monto_financiado * (interes_anual/100) * (dias_balance/365)
            ganancia_neta_lev = ganancia_bruta - interes_total
            roi_anualizado_lev = (ganancia_neta_lev / down_payment) / (dias_balance/365) if down_payment > 0 and dias_balance > 0 else 0
            pago_total = pago_mensual * (dias_balance / 30) if dias_balance > 0 else 0
        else:
            monto_financiado = 0
            down_payment = inversion_total
            ganancia_neta_lev = ganancia_bruta
            roi_anualizado_lev = roi_anualizado
            pago_mensual = 0
            pago_total = 0
        
        preferred = 0.08 * down_payment
        distrib_inv, distrib_mgmt = (0, 0)
        if ganancia_neta_lev > 0:
            if ganancia_neta_lev <= preferred:
                distrib_inv = ganancia_neta_lev
            else:
                excedente = ganancia_neta_lev - preferred
                distrib_inv = preferred + 0.75 * excedente
                distrib_mgmt = 0.25 * excedente
                
        resultados_dict[tipo_reforma] = {
            "PrecioVentaTotal": precio_venta_reformado,
            "PrecioCompraMax": precio_compra_max,
            "InversionTotal": inversion_total,
            "MontoFinanciado": monto_financiado, # Añadido
            "DownPayment": down_payment,
            "GastosAdquisicionFijos": gastos_adquisicion_fijos,
            "CostoReformaTotal": coste_reforma_total,
            "BrokerFee": broker_fee,
            "GananciaBruta": ganancia_bruta,
            "GananciaNetaLeveraged": ganancia_neta_lev,
            "ROI_anual": roi_anualizado,
            "ROI_anual_lev": roi_anualizado_lev,
            "DistribInversor": distrib_inv,
            "DistribManagement": distrib_mgmt,
            "Viable": roi_anualizado_lev >= 0.20 if porcentaje_financiado > 0 else roi_anualizado >= 0.20,
            "PagoMensual": pago_mensual,
            "PagoTotal": pago_total,
            "CostoReformaBase": coste_reforma_base,
            "IVA": iva_reforma
        }

    return resultados_dict

def generar_grafico_roi_viabilidad(m2, precio_m2_actual_reformado, precio_m2_noreformado_base, gastos_especiales, comision_venta_pct, broker_pct, porcentaje_financiado, interes_anual, dias_balance, roi_objetivo):
    precios_venta_m2 = np.arange(0, precio_m2_actual_reformado * 2, 25) # Comienza desde 0
    
    data = {'precio_m2_venta': [], 'roi_apalancado': []}
    
    for p_m2 in precios_venta_m2:
        try:
            resultados = calcular_resultados(
                m2=m2,
                precio_m2_reformado=p_m2, # Usamos el precio simulado como precio de venta
                precio_m2_noreformado=precio_m2_noreformado_base, # Mantenemos el noreformado base para referencia
                gastos_especiales=gastos_especiales,
                comision_venta_pct=comision_venta_pct,
                broker_pct=broker_pct,
                porcentaje_financiado=porcentaje_financiado,
                interes_anual=interes_anual,
                dias_balance=dias_balance,
                roi_objetivo=roi_objetivo
            )
            roi = resultados['Lavado de cara']['ROI_anual_lev']
            data['precio_m2_venta'].append(p_m2)
            data['roi_apalancado'].append(roi)
        except (ZeroDivisionError, KeyError): # Manejamos errores si el down payment es 0
            data['precio_m2_venta'].append(p_m2)
            data['roi_apalancado'].append(0)

    df = pd.DataFrame(data)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['precio_m2_venta'], y=df['roi_apalancado'] * 100,
                             mode='lines', name='ROI Anualizado Apalancado')) # Quité markers para una línea más suave

    # Línea de viabilidad en 20%
    fig.add_hline(y=20, line_dash="dash", line_color="red", annotation_text="Viabilidad (20% ROI)", annotation_position="bottom right")

    # Encuentra el punto de intersección
    try:
        # Filtramos solo los puntos donde el ROI es positivo o cumple la viabilidad
        df_viable_positive = df[(df['roi_apalancado'] >= 0.0) & (df['precio_m2_venta'] > 0)]
        if not df_viable_positive.empty:
            # Encontramos el primer precio donde el ROI apalancado es >= 20%
            viability_cross_idx = (df_viable_positive['roi_apalancado'] * 100 >= 20).idxmax()
            precio_viabilidad = df_viable_positive.loc[viability_cross_idx, 'precio_m2_venta']

            fig.add_vline(x=precio_viabilidad, line_dash="dash", line_color="green", annotation_text=f"Viable desde {precio_viabilidad:,.0f}€/m²", annotation_position="top left")
    except (IndexError, TypeError):
        pass # No se encontró punto de cruce

    fig.update_layout(title='Viabilidad de la Operación (ROI vs. Precio de Venta)',
                      xaxis_title='Precio de Venta por m² (€)',
                      yaxis_title='ROI Anualizado Apalancado (%)',
                      template="plotly_white" if st.session_state.theme == 'light' else "plotly_dark")
    
    return fig

def generar_grafico_punto_equilibrio_reforma(m2, precio_m2_reformado_base, gastos_especiales, comision_venta_pct, broker_pct, porcentaje_financiado, interes_anual, dias_balance, roi_objetivo):
    costes_m2_reforma = np.arange(0, 1500, 25) # Rango de costes de reforma por m2
    
    data = {'coste_m2_reforma': [], 'roi_apalancado': []}
    
    for coste_m2 in costes_m2_reforma:
        try:
            resultados_sim = calcular_resultados(
                m2=m2,
                precio_m2_reformado=precio_m2_reformado_base,
                precio_m2_noreformado=precio_m2_reformado_base, # Usamos el mismo como base, aunque no se usa directamente para el coste de reforma
                gastos_especiales=gastos_especiales,
                comision_venta_pct=comision_venta_pct,
                broker_pct=broker_pct,
                porcentaje_financiado=porcentaje_financiado,
                interes_anual=interes_anual,
                dias_balance=dias_balance,
                roi_objetivo=roi_objetivo,
                custom_reforma_coste_m2=coste_m2 # Pasamos el coste de reforma simulado
            )
            roi = resultados_sim['Lavado de cara']['ROI_anual_lev'] # Usamos cualquier escenario de reforma, ya que custom_reforma_coste_m2 lo sobrescribe
            data['coste_m2_reforma'].append(coste_m2)
            data['roi_apalancado'].append(roi)
        except (ZeroDivisionError, KeyError):
            data['coste_m2_reforma'].append(coste_m2)
            data['roi_apalancado'].append(0) # ROI 0 si hay error o división por cero

    df = pd.DataFrame(data)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['coste_m2_reforma'], y=df['roi_apalancado'] * 100,
                             mode='lines', name='ROI Apalancado'))
    
    fig.update_layout(
        title='Punto de Equilibrio de la Reforma (ROI vs. Coste de Reforma)',
        xaxis_title='Coste de Reforma por m² (€)',
        yaxis_title='ROI Anualizado Apalancado (%)',
        template="plotly_white" if st.session_state.theme == 'light' else "plotly_dark",
        legend=dict(x=0.01, y=0.99)
    )

    fig.add_hline(y=20, line_dash="dash", line_color="red", annotation_text="Viabilidad (20% ROI)", annotation_position="top right", yref="y1")
    
    # Encuentra el punto de cruce para el coste de reforma
    try:
        df_viable_reforma = df[df['roi_apalancado'] * 100 >= 20]
        if not df_viable_reforma.empty:
            coste_viabilidad_reforma = df_viable_reforma['coste_m2_reforma'].max() # Máximo coste para ser viable
            fig.add_vline(x=coste_viabilidad_reforma, line_dash="dash", line_color="green", annotation_text=f"Viable hasta {coste_viabilidad_reforma:,.0f}€/m²", annotation_position="bottom right")
    except (IndexError, TypeError):
        pass

    return fig

# -----------------------------
# Interfaz principal de Streamlit
# -----------------------------
st.title("🏡 Calculadora UrbenEye de Oportunidades Inmobiliarias")

with st.sidebar:
    st.header("Configuración Global")
    st.markdown("Ajusta los parámetros para el análisis.")
    st.button(f"Cambiar a Tema {'Claro' if st.session_state.theme == 'dark' else 'Oscuro'}", on_click=toggle_theme)
    st.markdown("---")
    roi_input = st.number_input("ROI objetivo (%)", value=25, step=1)
    roi_slider = st.slider("Mover ROI (%)", 0, 200, roi_input, step=1)
    dias_balance = st.number_input("Días en balance", value=200, step=10)

st.markdown("---")
with st.container():
    st.subheader("1. Datos de la Propiedad y Mercado")
    col1, col2, col3 = st.columns(3)
    with col1:
        m2 = st.number_input("Metros cuadrados (m²)", value=80, step=1)
    with col2:
        precio_m2_reformado = st.number_input("Precio venta/m² **reformado** (€)", value=3000, step=100)
    with col3:
        precio_m2_noreformado = st.number_input("Precio venta/m² **sin reformar** (€)", value=2500, step=100)

st.markdown("---")
with st.container():
    st.subheader("2. Costes de Operación y Financiación")
    col1, col2 = st.columns(2)
    with col1:
        gastos_especiales = st.number_input("Gastos especiales (€)", value=0, step=100)
        comision_venta_pct = st.selectbox("Comisión de venta (%)", [1, 3])
        broker_pct = st.number_input("Broker fee (%)", value=0.0, step=0.5)
    with col2:
        porcentaje_financiado = st.number_input("Porcentaje financiado (%)", value=75, min_value=0, max_value=100, step=1)
        interes_anual = st.number_input("Tasa de interés anual (%)", value=0.0, step=0.5)

st.markdown("---")
resultados = calcular_resultados(m2, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, porcentaje_financiado, interes_anual, dias_balance, roi_slider)
st.header("3. Análisis de la Oportunidad :chart_with_upwards_trend:")
st.markdown("### Precios de Venta")
col1, col2 = st.columns(2)
with col1:
    st.metric("Precio de Venta Reformado", f"{resultados['Lavado de cara']['PrecioVentaTotal']:,.0f} €")
with col2:
    st.metric("Precio de Venta sin Reforma", f"{resultados['Sin Reforma']['PrecioVentaTotal']:,.0f} €")

# Pestañas para los 4 escenarios
tab0, tab1, tab2, tab3 = st.tabs(["Sin Reforma", "Lavado de cara", "Reforma integral barata", "Reforma integral normal"])
def display_scenario(scenario_name, results):
    with st.container():
        st.subheader(f"Análisis de {scenario_name}")
        col_kpi1, col_kpi2 = st.columns(2)
        with col_kpi1:
            st.metric("Precio de Compra Máximo", f"{results['PrecioCompraMax']:,.0f} €")
        with col_kpi2:
            st.metric("Inversión Máxima Total", f"{results['InversionTotal']:,.0f} €")
        col_roi1, col_roi2 = st.columns(2)
        with col_roi1:
            st.metric("ROI Anualizado", f"{results['ROI_anual']*100:.1f}%")
        with col_roi2:
            st.metric("ROI Apalancado Anualizado", f"{results['ROI_anual_lev']*100:.1f}%")
        if results["Viable"]:
            st.success("✅ Operación VIABLE (ROI >= 20%)")
        else:
            st.error("❌ Operación NO VIABLE (ROI < 20%)")

        with st.expander("Detalle de ganancias, costes y flujos de caja"):
            st.markdown("#### Desglose de Inversión y Ganancias")
            st.metric("Inversión Inicial (Down Payment)", f"{results['DownPayment']:,.0f} €")
            st.metric("Monto Financiado", f"{results['MontoFinanciado']:,.0f} €")
            st.metric("Ganancia Bruta (No Apalancada)", f"{results['GananciaBruta']:,.0f} €")
            st.metric("Ganancia Neta (Apalancada)", f"{results['GananciaNetaLeveraged']:,.0f} €")
            st.metric("Ganancia Inversor", f"{results['DistribInversor']:,.0f} €")
            st.metric("Ganancia Management", f"{results['DistribManagement']:,.0f} €")
            st.markdown("---")
            st.markdown("#### Costes de Reforma")
            st.metric("Costo de Obra (sin IVA)", f"{results['CostoReformaBase']:,.0f} €")
            st.metric("IVA (21%)", f"{results['IVA']:,.0f} €")
            st.markdown("---")
            st.markdown("#### Flujo de Caja del Préstamo")
            st.metric("Cuota Mensual (Principal + Intereses)", f"{results['PagoMensual']:,.0f} €")
            st.metric("Pago Total Acumulado", f"{results['PagoTotal']:,.0f} €")

with tab0: display_scenario("Sin Reforma", resultados["Sin Reforma"])
with tab1: display_scenario("Lavado de cara", resultados["Lavado de cara"])
with tab2: display_scenario("Reforma integral barata", resultados["Reforma integral barata"])
with tab3: display_scenario("Reforma integral normal", resultados["Reforma integral normal"])

st.markdown("---")

st.subheader("Comparativa de Escenarios y Viabilidad :bar_chart:")

# Gráfico de 3 tartas con Inversión
st.markdown("#### 📊 Distribución de la Inversión por Escenario de Reforma")
col_grafico1, col_grafico2, col_grafico3 = st.columns(3)

def create_pie_chart_inversion(scenario_name, results):
    df_chart = pd.DataFrame({
        'Componente': ['Precio de Compra Máximo', 'Gastos de Adquisición', 'Costo de Reforma (Total)', 'Broker Fee'],
        'Monto': [results['PrecioCompraMax'], results['GastosAdquisicionFijos'], results['CostoReformaTotal'], results['BrokerFee']]
    })
    fig = px.pie(df_chart, values='Monto', names='Componente',
                 title=f'{scenario_name}',
                 color_discrete_sequence=px.colors.sequential.RdBu) # Usamos una secuencia de colores
    fig.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
    fig.update_layout(showlegend=False,
                      template="plotly_white" if st.session_state.theme == 'light' else "plotly_dark")
    return fig

with col_grafico1:
    fig1 = create_pie_chart_inversion("Lavado de cara", resultados["Lavado de cara"])
    st.plotly_chart(fig1, use_container_width=True)

with col_grafico2:
    fig2 = create_pie_chart_inversion("Reforma integral barata", resultados["Reforma integral barata"])
    st.plotly_chart(fig2, use_container_width=True)

with col_grafico3:
    fig3 = create_pie_chart_inversion("Reforma integral normal", resultados["Reforma integral normal"])
    st.plotly_chart(fig3, use_container_width=True)

st.markdown("---")

# Gráfico de Viabilidad
st.markdown("#### 📈 Gráfico de Viabilidad (ROI vs. Precio de Venta)")
fig_viabilidad = generar_grafico_roi_viabilidad(m2, precio_m2_reformado, precio_m2_noreformado, gastos_especiales, comision_venta_pct, broker_pct, porcentaje_financiado, interes_anual, dias_balance, roi_slider)
st.plotly_chart(fig_viabilidad, use_container_width=True)

# Gráfico de Punto de Equilibrio de la Reforma
st.markdown("#### ⚖️ Gráfico de Punto de Equilibrio de la Reforma")
fig_equilibrio = generar_grafico_punto_equilibrio_reforma(m2, precio_m2_reformado, gastos_especiales, comision_venta_pct, broker_pct, porcentaje_financiado, interes_anual, dias_balance, roi_slider)
st.plotly_chart(fig_equilibrio, use_container_width=True)

with st.expander("Detalles completos del cálculo"):
    st.json(resultados)