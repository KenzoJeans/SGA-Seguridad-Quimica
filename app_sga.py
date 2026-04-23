import re
import io
import requests
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
    :root {
        --verde:   #2e7d32;
        --rojo:    #c62828;
        --amarillo:#f57f17;
        --gris:    #455a64;
    }
    h1 { color: #1a237e !important; letter-spacing: -0.5px; }
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
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 6px; }
    .info-item { font-size: 0.9em; color: #37474f; }
    .info-label { font-weight: 600; color: #263238; }
    .sidebar-metric { font-size: 0.85em; color: #546e7a; margin-bottom: 2px; }
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
# CONFIGURACIÓN DEL GOOGLE SHEET (entrada flexible)
# ─────────────────────────────────────────────
# Puedes pegar aquí la URL completa del Google Sheet compartido (la que proporcionaste).
# Ejemplo:
# https://docs.google.com/spreadsheets/d/1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ/edit?usp=sharing
SHEET_URL = "https://docs.google.com/spreadsheets/d/1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ/edit?usp=sharing"

# ─────────────────────────────────────────────
# UTILIDADES: extraer ID y GID de distintas variantes de URL
# ─────────────────────────────────────────────
def parse_sheet_url(url: str):
    """
    Extrae sheet_id y gid desde una URL de Google Sheets.
    Devuelve (sheet_id, gid). Si no encuentra gid, devuelve '0'.
    """
    if not isinstance(url, str) or url.strip() == "":
        return None, None

    # Buscar ID entre /d/ y / (edit o view)
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    sheet_id = m.group(1) if m else None

    # Buscar gid en query string o en fragmento
    m_gid = re.search(r"[?&]gid=(\d+)", url)
    if not m_gid:
        m_gid = re.search(r"#gid=(\d+)", url)
    gid = m_gid.group(1) if m_gid else "0"

    return sheet_id, gid

def build_csv_export_url(sheet_id: str, gid: str = "0") -> str:
    """
    Construye la URL de exportación CSV para Google Sheets.
    """
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

# ─────────────────────────────────────────────
# Nombres de columnas esperadas
# ─────────────────────────────────────────────
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

# ─────────────────────────────────────────────
# CARGA DE DATOS: usa requests para mayor control y manejo de errores
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(sheet_url: str) -> pd.DataFrame:
    sheet_id, gid = parse_sheet_url(sheet_url)
    if not sheet_id:
        raise ValueError("No se pudo extraer el ID del Google Sheet desde la URL proporcionada.")

    csv_url = build_csv_export_url(sheet_id, gid)

    # Hacer la petición con headers para evitar bloqueos por user-agent
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0; +https://example.com)",
        "Accept": "text/csv, */*; q=0.1",
    }

    try:
        resp = requests.get(csv_url, headers=headers, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        raise ConnectionError(f"Error de conexión al intentar descargar el CSV: {e}")

    # Si Google devuelve redirección a página de login o error, mostrar detalle
    if resp.status_code != 200:
        # Incluir fragmento del contenido para diagnóstico (sin exponer todo)
        snippet = resp.text[:500].replace("\n", " ")
        raise ConnectionError(
            f"Respuesta inesperada al solicitar el CSV (HTTP {resp.status_code}). "
            f"Contenido: {snippet}"
        )

    # Leer CSV desde el texto recibido
    try:
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as e:
        # Si pandas no puede parsear, mostrar un fragmento para diagnóstico
        snippet = resp.text[:1000].replace("\n", " ")
        raise ValueError(f"El contenido descargado no parece ser un CSV válido. Fragmento: {snippet}") from e

    # Normalizar nombres de columnas (quitar espacios)
    df.columns = [c.strip() for c in df.columns]

    # Asegurar que existan las columnas esperadas; si faltan, crearlas vacías
    expected_cols = [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]
    for col in expected_cols:
        if col not in df.columns:
            if col == COL_VIGENCIA:
                df[col] = ""
            else:
                df[col] = pd.NA

    # Normalizaciones seguras
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").astype(str).str.strip().str.upper()
    df[COL_FAMILIA]  = df[COL_FAMILIA].fillna("SIN FAMILIA").astype(str).str.strip().str.upper()
    df[COL_SUSTANCIA] = df[COL_SUSTANCIA].fillna("").astype(str).str.strip()
    df[COL_URL] = df[COL_URL].fillna("").astype(str).str.strip()
    df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).str.strip()

    return df

# ─────────────────────────────────────────────
# Intentar cargar datos y manejar errores con mensajes útiles
# ─────────────────────────────────────────────
try:
    df = cargar_datos(SHEET_URL)
except Exception as e:
    st.error(
        "❌ No se pudo leer el Google Sheet. Verifica lo siguiente:\n\n"
        "1) La URL que pegaste contiene el ID correcto del Sheet.\n"
        "2) El Sheet está compartido como 'Cualquier persona con el enlace → Lector'.\n"
        "3) Si usas una cuenta corporativa, puede que Google requiera autenticación; "
        "en ese caso publica la hoja o usa una cuenta con acceso público.\n\n"
        "Detalle técnico (útil para diagnóstico):"
    )
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# SIDEBAR – FILTROS
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔎 Filtros")

    busqueda = st.text_input(
        "Buscar sustancia",
        placeholder="Ej: ÁCIDO OXÁLICO, SODA…",
        help="Búsqueda parcial, sin importar mayúsculas.",
    )

    familias_disponibles = sorted(df[COL_FAMILIA].replace("", "SIN FAMILIA").unique().tolist())
    familias_sel = st.multiselect(
        "Familia / categoría",
        options=familias_disponibles,
        default=[],
        placeholder="Todas las familias",
    )

    estado_sel = st.radio(
        "Estado de vigencia",
        options=["Todos", "✅ Vigentes", "⚠️ No vigentes"],
        index=0,
    )

    st.divider()

    total      = len(df)
    vigentes   = (df[COL_VIGENCIA] == "VIGENTE").sum()
    novigentes = total - vigentes
    st.markdown(f"**📦 Total fichas:** {total}")
    st.markdown(f"**✅ Vigentes:** {vigentes}")
    st.markdown(f"**⚠️ No vigentes:** {novigentes}")

    st.divider()
    if st.button("🔄 Recargar datos"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.experimental_rerun()

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_filtrado = df.copy()

if busqueda and busqueda.strip():
    mask = df_filtrado[COL_SUSTANCIA].astype(str).str.contains(busqueda.strip(), case=False, na=False)
    df_filtrado = df_filtrado[mask]

if familias_sel:
    df_filtrado = df_filtrado[df_filtrado[COL_FAMILIA].isin(familias_sel)]

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
            st.markdown(f'<span class="{badge_cls}">{badge_txt}</span>', unsafe_allow_html=True)
            st.write("")
            st.markdown(f"🏭 **Familia / Categoría:** {familia}")
            st.markdown(f"📅 **Última revisión:** {fecha_fmt}")
            st.markdown(f"📄 **Vigencia:** {badge_txt}")

        with col_accion:
            tiene_picto = isinstance(url_picto, str) and url_picto.strip() != "" and url_picto.strip().startswith("http")
            if tiene_picto:
                st.image(url_picto.strip(), caption="Pictograma SGA", width=120)
            else:
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

            tiene_url = isinstance(url_doc, str) and url_doc.strip() != "" and url_doc.strip().startswith("http")
            if tiene_url:
                try:
                    st.link_button("📂 Abrir ficha de seguridad", url_doc.strip(), use_container_width=True)
                except Exception:
                    st.markdown(f"[📂 Abrir ficha de seguridad]({url_doc.strip()})")
            else:
                st.warning("🔗 Enlace no disponible")

            if not es_vigente:
                st.error("Documento **no vigente** o pendiente de actualización.")

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
