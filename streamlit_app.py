import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SGA – Kenzo Jeans",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# ESTILOS PERSONALIZADOS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Paleta industrial / textil */
    :root {
        --verde:   #2e7d32;
        --rojo:    #c62828;
        --amarillo:#f57f17;
        --gris:    #455a64;
    }

    /* Encabezado principal */
    h1 { color: #1a237e !important; letter-spacing: -0.5px; }

    /* Badge vigencia */
    .badge-vigente {
        background: #e8f5e9; color: #2e7d32;
        border: 1.5px solid #2e7d32;
        border-radius: 20px; padding: 2px 12px;
        font-weight: 700; font-size: 0.78em;
    }
    .badge-novigente {
        background: #ffebee; color: #c62828;
        border: 1.5px solid #c62828;
        border-radius: 20px; padding: 2px 12px;
        font-weight: 700; font-size: 0.78em;
    }

    /* Tarjeta de detalle */
    .info-grid {
        display: grid; grid-template-columns: 1fr 1fr;
        gap: 8px; margin-top: 6px;
    }
    .info-item { font-size: 0.9em; color: #37474f; }
    .info-label { font-weight: 600; color: #263238; }

    /* Fila de métricas en sidebar */
    .sidebar-metric { font-size: 0.85em; color: #546e7a; margin-bottom: 2px; }

    /* Expander: quitar borde raro en algunos temas */
    details summary { font-size: 1.02em !important; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TÍTULO
# ─────────────────────────────────────────────
col_logo, col_title = st.columns([1, 9])
with col_logo:
    st.markdown("## 🛡️")
with col_title:
    st.title("Repositorio Hojas de Seguridad — SGA")
    st.caption("Sistema Globalmente Armonizado · Kenzo Jeans · Consulta rápida de fichas de seguridad químicas")

st.divider()

# ─────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────
URL_SHEET = "https://docs.google.com/spreadsheets/d/1XwmNLHeeoD3UW41LvfltLA1m4ZexweNi/view"

# Nombre exacto de la columna URL en el Sheet
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"   # ← nombre real en el Sheet
COL_PICTO     = "PICTOGRAMA"                 # URL de imagen si existe

@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(url: str) -> pd.DataFrame:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=url, usecols=list(range(6)), ttl=600)
    df.columns = [c.strip() for c in df.columns]   # limpiar espacios
    # Normalizar vigencia
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").str.strip().str.upper()
    # Normalizar familia
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("SIN FAMILIA").str.strip().str.upper()
    return df

try:
    df = cargar_datos(URL_SHEET)
except Exception as e:
    st.error(
        "❌ No se pudo conectar con Google Sheets. "
        "Verifica que el enlace sea público y que `st.secrets` tenga las credenciales correctas."
    )
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# SIDEBAR – FILTROS
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔎 Filtros")

    # Buscador de texto
    busqueda = st.text_input(
        "Buscar sustancia",
        placeholder="Ej: ÁCIDO OXÁLICO, SODA…",
        help="Búsqueda parcial, sin importar mayúsculas.",
    )

    # Filtro de familia
    familias_disponibles = sorted(df[COL_FAMILIA].unique().tolist())
    familias_sel = st.multiselect(
        "Familia / categoría",
        options=familias_disponibles,
        default=[],
        placeholder="Todas las familias",
    )

    # Filtro de vigencia
    estado_sel = st.radio(
        "Estado de vigencia",
        options=["Todos", "✅ Vigentes", "⚠️ No vigentes"],
        index=0,
    )

    st.divider()

    # Métricas rápidas
    total      = len(df)
    vigentes   = (df[COL_VIGENCIA] == "VIGENTE").sum()
    novigentes = total - vigentes
    st.markdown(f"**📦 Total fichas:** {total}")
    st.markdown(f"**✅ Vigentes:** {vigentes}")
    st.markdown(f"**⚠️ No vigentes:** {novigentes}")

    st.divider()
    if st.button("🔄 Recargar datos"):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_filtrado = df.copy()

# Filtro texto
if busqueda.strip():
    mask = df_filtrado[COL_SUSTANCIA].str.contains(
        busqueda.strip(), case=False, na=False
    )
    df_filtrado = df_filtrado[mask]

# Filtro familia
if familias_sel:
    df_filtrado = df_filtrado[df_filtrado[COL_FAMILIA].isin(familias_sel)]

# Filtro estado
if estado_sel == "✅ Vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] == "VIGENTE"]
elif estado_sel == "⚠️ No vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] != "VIGENTE"]

# ─────────────────────────────────────────────
# RESULTADOS – encabezado
# ─────────────────────────────────────────────
n = len(df_filtrado)
if n == 0:
    st.warning("⚠️ No se encontraron fichas con los filtros aplicados.")
    st.stop()

st.markdown(f"**{n} ficha{'s' if n != 1 else ''} encontrada{'s' if n != 1 else ''}**")
st.caption("Haz clic en el nombre de la sustancia para ver el detalle completo.")

# ─────────────────────────────────────────────
# TARJETAS EXPANDIBLES
# ─────────────────────────────────────────────
for _, row in df_filtrado.iterrows():
    sustancia = str(row.get(COL_SUSTANCIA, "—")).strip()
    familia   = str(row.get(COL_FAMILIA,   "—")).strip()
    fecha     = row.get(COL_FECHA, None)
    vigencia  = str(row.get(COL_VIGENCIA,  "")).strip().upper()
    url_doc   = row.get(COL_URL,  None)
    url_picto = row.get(COL_PICTO, None)

    es_vigente = vigencia == "VIGENTE"
    emoji_est  = "✅" if es_vigente else "⚠️"
    badge_cls  = "badge-vigente" if es_vigente else "badge-novigente"
    badge_txt  = vigencia if vigencia else "SIN DATO"
    fecha_fmt  = str(fecha).strip() if pd.notna(fecha) and str(fecha).strip() not in ("", "nan") else "Sin fecha"

    expander_label = f"{emoji_est}  {sustancia}  ·  {familia}"

    with st.expander(expander_label, expanded=False):
        col_info, col_accion = st.columns([3, 2])

        with col_info:
            # Badge de vigencia
            st.markdown(
                f'<span class="{badge_cls}">{badge_txt}</span>',
                unsafe_allow_html=True,
            )
            st.write("")

            st.markdown(f"🏭 **Familia / Categoría:** {familia}")
            st.markdown(f"📅 **Última revisión:** {fecha_fmt}")
            st.markdown(f"📄 **Vigencia:** {badge_txt}")

        with col_accion:
            # Pictograma SGA (si hay URL de imagen)
            tiene_picto = (
                pd.notna(url_picto)
                and str(url_picto).strip().startswith("http")
            )
            if tiene_picto:
                st.image(
                    str(url_picto).strip(),
                    caption="Pictograma SGA",
                    width=120,
                )
            else:
                # Pictograma genérico SVG si no hay imagen definida
                st.markdown("""
                <div style="
                    width:90px; height:90px;
                    border: 3px solid #e53935;
                    border-radius: 8px;
                    display:flex; align-items:center; justify-content:center;
                    font-size:2.2em; background:#fff3e0;
                ">⚗️</div>
                """, unsafe_allow_html=True)

            st.write("")

            # Botón de enlace
            tiene_url = (
                pd.notna(url_doc)
                and str(url_doc).strip().startswith("http")
            )
            if tiene_url:
                st.link_button(
                    "📂 Abrir ficha de seguridad",
                    str(url_doc).strip(),
                    use_container_width=True,
                )
            else:
                st.warning("🔗 Enlace no disponible")

            # Alerta adicional si no está vigente
            if not es_vigente:
                st.error("Documento **no vigente** o pendiente de actualización.")

    # Separador sutil entre fichas
    st.markdown("<hr style='margin:2px 0; border-color:#eceff1'>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# PIE DE PÁGINA
# ─────────────────────────────────────────────
st.divider()
st.caption(
    "🛡️ **Kenzo Jeans – Gestión SGA** · "
    "Los documentos se actualizan desde Google Sheets · "
    "Para reportar un error contacta al área de SST."
)
