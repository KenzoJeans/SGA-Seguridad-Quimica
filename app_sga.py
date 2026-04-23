# app_sga_streamlit.py
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
# ESTILOS (resumido)
# ─────────────────────────────────────────────
st.markdown("""
<style>
h1 { color: #1a237e !important; }
.badge-vigente { background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:4px 10px; font-weight:700; }
.badge-novigente { background:#ffebee; color:#c62828; border-radius:20px; padding:4px 10px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTES: nombres de columnas esperadas
# ─────────────────────────────────────────────
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

# ─────────────────────────────────────────────
# UTILIDADES: parseo de URL/ID y construcción de URLs CSV
# ─────────────────────────────────────────────
def parse_sheet_url(url: str):
    """Extrae sheet_id y gid desde una URL de Google Sheets o devuelve (id, '0') si se pasa solo el id."""
    if not url or not isinstance(url, str):
        return None, None
    s = url.strip()
    # Extraer ID entre /d/ y siguiente /
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", s)
    sheet_id = m.group(1) if m else None
    # Si no hay /d/ quizá el usuario pegó solo el ID
    if not sheet_id and re.fullmatch(r"[a-zA-Z0-9-_]+", s):
        sheet_id = s
    # Extraer gid si existe
    m_gid = re.search(r"[?&]gid=(\d+)", s) or re.search(r"#gid=(\d+)", s)
    gid = m_gid.group(1) if m_gid else "0"
    return sheet_id, gid

def build_candidate_csv_urls(sheet_id: str, gid: str = "0"):
    """Genera varias variantes de URL para intentar descargar CSV desde Google Sheets."""
    urls = []
    if not sheet_id:
        return urls
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")
    return urls

def try_download_csv(urls, timeout=15):
    """Intenta descargar el CSV probando varias URLs; devuelve (text, error_msg)."""
    last_err = None
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0)",
        "Accept": "text/csv, */*; q=0.1",
    }
    for u in urls:
        try:
            resp = requests.get(u, headers=headers, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            text = resp.text
            # detectar si Google devolvió HTML (página de login o error)
            if text.strip().lower().startswith("<!doctype html") or ("login" in text.lower() and "google" in text.lower()):
                last_err = f"Respuesta no es CSV válida desde {u}"
                continue
            return text, None
        except requests.HTTPError as he:
            code = he.response.status_code if he.response is not None else "HTTPError"
            last_err = f"HTTP {code} desde {u}"
        except Exception as e:
            last_err = f"Error descargando {u}: {e}"
    return None, last_err

# ─────────────────────────────────────────────
# CARGA Y NORMALIZACIÓN DE DATOS
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos_from_sheet_input(sheet_input: str, uploaded_csv_text: str | None = None) -> pd.DataFrame:
    """
    sheet_input: puede ser URL completa o solo el sheet_id.
    uploaded_csv_text: si el usuario subió un CSV, se prioriza.
    """
    csv_text = None
    download_error = None

    # Priorizar archivo subido (texto CSV ya decodificado)
    if uploaded_csv_text:
        csv_text = uploaded_csv_text
    else:
        # Intentar parsear sheet_input y descargar
        sheet_id, gid = parse_sheet_url(sheet_input or "")
        if not sheet_id:
            raise ValueError("No se pudo extraer el ID del Google Sheet desde la entrada proporcionada.")
        urls = build_candidate_csv_urls(sheet_id, gid)
        if not urls:
            raise ValueError("No se pudo construir una URL válida para descargar el CSV.")
        csv_text, download_error = try_download_csv(urls, timeout=15)
        if csv_text is None:
            raise ConnectionError(f"No se pudo descargar CSV: {download_error}")

    # Parsear CSV con pandas
    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as e:
        snippet = (csv_text or "")[:1000].replace("\n", " ")
        raise ValueError(f"El contenido descargado no parece ser un CSV válido. Fragmento: {snippet}") from e

    # Normalizar nombres de columnas
    df.columns = [c.strip() for c in df.columns]

    # Asegurar existencia de columnas esperadas para evitar KeyError
    expected_cols = [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]
    for col in expected_cols:
        if col not in df.columns:
            # VIGENCIA la dejamos como cadena vacía por defecto
            df[col] = "" if col == COL_VIGENCIA else pd.NA

    # Normalizaciones seguras
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").astype(str).str.strip().str.upper()
    df[COL_FAMILIA]  = df[COL_FAMILIA].fillna("SIN FAMILIA").astype(str).str.strip().str.upper()
    df[COL_SUSTANCIA] = df[COL_SUSTANCIA].fillna("").astype(str).str.strip()
    df[COL_URL] = df[COL_URL].fillna("").astype(str).str.strip()
    df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).str.strip()

    return df

# ─────────────────────────────────────────────
# INTERFAZ: entrada de URL/ID y subida de CSV (fallback)
# ─────────────────────────────────────────────
st.title("Repositorio Hojas de Seguridad — SGA")
st.caption("Sistema Globalmente Armonizado · Kenzo Jeans · Consulta rápida de fichas de seguridad químicas")
st.divider()

with st.sidebar:
    st.header("🔎 Fuente de datos (Google Sheets)")
    st.markdown("Pega la URL completa del Google Sheet o solo el ID. Si la descarga falla, sube el CSV manualmente.")
    sheet_input = st.text_input("URL o ID del Google Sheet", value="https://docs.google.com/spreadsheets/d/1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ/edit?usp=sharing")
    st.markdown("---")
    uploaded_file = st.file_uploader("Subir CSV exportado (opcional)", type=["csv"])
    if st.button("🔄 Recargar datos"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.experimental_rerun()

# Decodificar archivo subido si existe
uploaded_csv_text = None
if uploaded_file is not None:
    try:
        uploaded_csv_text = uploaded_file.getvalue().decode("utf-8")
    except Exception:
        try:
            uploaded_csv_text = uploaded_file.getvalue().decode("latin-1")
        except Exception as e:
            st.error(f"No se pudo leer el archivo subido: {e}")
            st.stop()

# Intentar cargar datos
try:
    df = cargar_datos_from_sheet_input(sheet_input, uploaded_csv_text)
except Exception as e:
    st.error(
        "❌ No se pudo leer el Google Sheet. Verifica:\n"
        "1) La URL/ID es correcta.\n"
        "2) El Sheet está compartido como 'Cualquier persona con el enlace → Lector'.\n"
        "3) Si tu organización requiere autenticación, publica la hoja o sube el CSV manualmente."
    )
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# SIDEBAR: filtros y métricas
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔎 Filtros")
    busqueda = st.text_input("Buscar sustancia", placeholder="Ej: ÁCIDO OXÁLICO, SODA…")
    familias_disponibles = sorted(df[COL_FAMILIA].replace("", "SIN FAMILIA").unique().tolist())
    familias_sel = st.multiselect("Familia / categoría", options=familias_disponibles, default=[])
    estado_sel = st.radio("Estado de vigencia", options=["Todos", "✅ Vigentes", "⚠️ No vigentes"], index=0)
    st.divider()
    total = len(df)
    vigentes = (df[COL_VIGENCIA] == "VIGENTE").sum()
    novigentes = total - vigentes
    st.markdown(f"**📦 Total fichas:** {total}")
    st.markdown(f"**✅ Vigentes:** {vigentes}")
    st.markdown(f"**⚠️ No vigentes:** {novigentes}")

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_filtrado = df.copy()

if busqueda and busqueda.strip():
    df_filtrado = df_filtrado[df_filtrado[COL_SUSTANCIA].astype(str).str.contains(busqueda.strip(), case=False, na=False)]

if familias_sel:
    df_filtrado = df_filtrado[df_filtrado[COL_FAMILIA].isin(familias_sel)]

if estado_sel == "✅ Vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] == "VIGENTE"]
elif estado_sel == "⚠️ No vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] != "VIGENTE"]

# ─────────────────────────────────────────────
# RESULTADOS
# ─────────────────────────────────────────────
n = len(df_filtrado)
if n == 0:
    st.warning("⚠️ No se encontraron fichas con los filtros aplicados.")
    st.stop()

st.markdown(f"**{n} ficha{'s' if n != 1 else ''} encontrada{'s' if n != 1 else ''}**")
st.caption("Haz clic en el nombre de la sustancia para ver el detalle completo.")

for _, row in df_filtrado.iterrows():
    sustancia = str(row.get(COL_SUSTANCIA, "—")).strip() or "—"
    familia = str(row.get(COL_FAMILIA, "—")).strip() or "—"
    fecha = row.get(COL_FECHA, None)
    vigencia = str(row.get(COL_VIGENCIA, "")).strip().upper()
    url_doc = row.get(COL_URL, "")
    url_picto = row.get(COL_PICTO, "")

    es_vigente = vigencia == "VIGENTE"
    emoji_est = "✅" if es_vigente else "⚠️"
    badge_cls = "badge-vigente" if es_vigente else "badge-novigente"
    badge_txt = vigencia if vigencia else "SIN DATO"
    fecha_fmt = str(fecha).strip() if pd.notna(fecha) and str(fecha).strip() not in ("", "nan") else "Sin fecha"

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
            tiene_picto = isinstance(url_picto, str) and url_picto.strip().startswith("http")
            if tiene_picto:
                try:
                    st.image(url_picto.strip(), caption="Pictograma SGA", width=120)
                except Exception:
                    st.write("Pictograma no disponible")
            else:
                st.markdown("<div style='width:90px;height:90px;border:3px solid #e53935;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2.2em;background:#fff3e0;'>⚗️</div>", unsafe_allow_html=True)

            st.write("")
            tiene_url = isinstance(url_doc, str) and url_doc.strip().startswith("http")
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

st.divider()
st.caption("🛡️ Kenzo Jeans – Gestión SGA · Los documentos se actualizan desde Google Sheets")
