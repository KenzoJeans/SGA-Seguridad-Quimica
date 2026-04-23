import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# Configuración de página
st.set_page_config(page_title="Seguridad Química - Kenzo Jeans", layout="wide")

# Mostrar Logo
st.image("logo-white-kenzo.png", width=200)

st.title("🛡️ Panel de Control de Seguridad Química")

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)
df = conn.read()

st.write("### Inventario de Productos Químicos")
st.dataframe(df)
