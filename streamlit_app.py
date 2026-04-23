import streamlit as st
from st_gsheets_connection import GSheetsConnection # <--- Cambia esta línea
import pandas as pd
st.set_page_config(page_title="SGA - Kenzo Jeans", page_icon="🛡️", layout="wide")
st.title("🛡️ Repositorio Hojas de Seguridad (SGA)")
st.markdown("Consulta rápida de documentos para la planta y PTAR.")
# URL de tu Google Sheet (Asegúrate de que esté compartido como 'Lector' para cualquier persona con el enlace)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1XwmNLHeeoD3UW41LvfltLA1m4ZexweNi/view" 
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # Leemos la hoja (puedes ajustar el nombre de la pestaña si es necesario)
    df = conn.read(spreadsheet=URL_SHEET)

    # Buscador por nombre de sustancia
    busqueda = st.text_input("🔍 Buscar por nombre del químico:", placeholder="Ej: ÁCIDO OXÁLICO")
    if busqueda:
        # Filtramos en la columna exacta de tu imagen
        resultado = df[df['SUSTANCIA/QUÍMICO'].str.contains(busqueda, case=False, na=False)]

        if not resultado.empty:
            for index, row in resultado.iterrows():
                # Color según vigencia
                es_vigente = str(row['VIGENCIA']).strip().upper() == "VIGENTE"
                color = "green" if es_vigente else "red"
                emoji = "✅" if es_vigente else "⚠️"
                with st.expander(f"{emoji} {row['SUSTANCIA/QUÍMICO']} - {row['FAMILIA']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Estado:** :{color}[{row['VIGENCIA']}]")
                        st.write(f"**Última revisión:** {row['FECHA'] if pd.notna(row['FECHA']) else 'Sin fecha'}")

                    with col2:
                        url_doc = row['URL']
                        if pd.notna(url_doc) and str(url_doc).startswith("http"):
                            st.link_button("📂 Abrir Hoja de Seguridad", url_doc)
                        else:
                            st.warning("Enlace no disponible")
        else:
            st.error("No se encontraron coincidencias.")
    else:
        st.info("Escribe el nombre de un químico para ver su información y descargar el PDF.")
except Exception as e:
    st.error("Error al conectar con los datos. Revisa que el enlace de Google Sheets sea público.")
