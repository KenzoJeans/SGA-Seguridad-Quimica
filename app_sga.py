import streamlit as st
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
# ──────────────────────────────────────────────────────────────────
# ⚠️  INSTRUCCIÓN: coloca solo el ID del Sheet (la parte entre /d/ y /edit)
# ──────────────────────────────────────────────────────────────────
# ID extraído de:
# https://docs.google.com/spreadsheets/d/1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ/edit?usp=sharing
SHEET_ID  = "1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ"   # ← solo el ID, sin /edit...
SHEET_GID = "0"                                            # pestaña 0 = primera hoja

# URL de exportación CSV directa — formato correcto para Google Sheets
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# Nombres de columnas (deben coincidir exactamente con la fila 1 del Sheet)
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(csv_url: str) -> pd.DataFrame:
    """
    Lee el CSV exportado desde Google Sheets y normaliza columnas clave.
    Se agregan columnas vacías si faltan para evitar KeyError.
    """
    # Leer CSV (si la URL está mal, pandas leerá HTML o fallará)
    df = pd.read_csv(csv_url)

    # Normalizar nombres de columnas (quitar espacios extras)
    df.columns = [c.strip() for c in df.columns]

    # Asegurar que existan las columnas esperadas; si faltan, crearlas vacías
    expected_cols = [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]
    for col in expected_cols:
        if col not in df.columns:
            # Crear columna con valores nulos (o cadena vacía para VIGENCIA)
            if col == COL_VIGENCIA:
                df[col] = ""
            else:
                df[col] = pd.NA

    # Normalizar campos clave sin lanzar KeyError
    # VIGENCIA: convertir a mayúsculas, quitar espacios y rellenar vacíos
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").astype(str).str.strip().str.upper()

    # FAMILIA: rellenar con valor por defecto si falta
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("SIN FAMILIA").astype(str).str.strip().str.upper()

    # SUSTANCIA: asegurar tipo string y quitar espacios
    df[COL_SUSTANCIA] = df[COL_SUSTANCIA].fillna("").astype(str).str.strip()

    # URL y PICTOGRAMA: limpiar espacios
    df[COL_URL] = df[COL_URL].fillna("").astype(str).str.strip()
    df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).str.strip()

    return df

try:
    df = cargar_datos(CSV_URL)
except Exception as e:
    st.error(
        "❌ No se pudo leer el Google Sheet. "
        "Verifica que: (1) el SHEET_ID sea correcto (solo el ID), "
        "(2) el Sheet esté compartido como público (Lector), "
        "y (3) la pestaña (gid) sea la correcta."
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
    familias_disponibles = sorted(df[COL_FAMILIA].replace("", "SIN FAMILIA").unique().tolist())
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

    # Métricas rápidas (usar columnas ya garantizadas)
    total      = len(df)
    vigentes   = (df[COL_VIGENCIA] == "VIGENTE").sum()
    novigentes = total - vigentes
    st.markdown(f"**📦 Total fichas:** {total}")
    st.markdown(f"**✅ Vigentes:** {vigentes}")
    st.markdown(f"**⚠️ No vigentes:** {novigentes}")

    st.divider()
    if st.button("🔄 Recargar datos"):
        # Limpiar cache y recargar
        try:
            st.cache_data.clear()
        except Exception:
            # En caso de que la API cambie, forzamos rerun igualmente
            pass
        st.experimental_rerun()

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_filtrado = df.copy()

# Filtro texto (si la columna SUSTANCIA/QUÍMICO está vacía, evitar error)
if busqueda and busqueda.strip():
    mask = df_filtrado[COL_SUSTANCIA].astype(str).str.contains(
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
    sustancia = str(row.get(COL_SUSTANCIA, "—")).strip() or "—"
    familia   = str(row.get(COL_FAMILIA,   "—")).strip() or "—"
    fecha     = row.get(COL_FECHA, None)
    vigencia  = str(row.get(COL_VIGENCIA,  "")).strip().upper()
    url_doc   = row.get(COL_URL,  "")
    url_picto = row.get(COL_PICTO, "")

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
                isinstance(url_picto, str)
                and url_picto.strip() != ""
                and url_picto.strip().startswith("http")
            )
            if tiene_picto:
                st.image(
                    url_picto.strip(),
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
                isinstance(url_doc, str)
                and url_doc.strip() != ""
                and url_doc.strip().startswith("http")
            )
            if tiene_url:
                # st.link_button está disponible en versiones recientes de Streamlit
                try:
                    st.link_button(
                        "📂 Abrir ficha de seguridad",
                        url_doc.strip(),
                        use_container_width=True,
                    )
                except Exception:
                    # Fallback: mostrar enlace como markdown
                    st.markdown(f"[📂 Abrir ficha de seguridad]({url_doc.strip()})")
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
