# app_sga.py
import re
import io
import requests
import streamlit as st
import pandas as pd
from typing import Tuple

# ─────────────────────────────────────────────
# Configuración página
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SGA – Kenzo Jeans",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos ligeros
st.markdown(
    """
<style>
.card-title { font-size:1.05rem; font-weight:700; margin:0 0 6px 0; }
.detail-label { font-weight:700; color:#263238; }
.badge-vigente { background:#e8f5e9; color:#2e7d32; border-radius:12px; padding:4px 10px; font-weight:700; }
.badge-novigente { background:#ffebee; color:#c62828; border-radius:12px; padding:4px 10px; font-weight:700; }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Columnas esperadas (exactas según tu Sheet)
# ─────────────────────────────────────────────
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

# ─────────────────────────────────────────────
# Utilidades para Google Sheets
# ─────────────────────────────────────────────
def parse_sheet_url(url: str) -> Tuple[str, str]:
    """Extrae sheet_id y gid desde una URL o devuelve (id, '0') si se pasa solo el id."""
    if not url or not isinstance(url, str):
        return None, None
    s = url.strip()
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", s)
    sheet_id = m.group(1) if m else None
    if not sheet_id and re.fullmatch(r"[a-zA-Z0-9-_]+", s):
        sheet_id = s
    m_gid = re.search(r"[?&]gid=(\d+)", s) or re.search(r"#gid=(\d+)", s)
    gid = m_gid.group(1) if m_gid else "0"
    return sheet_id, gid

def build_candidate_csv_urls(sheet_id: str, gid: str = "0"):
    urls = []
    if not sheet_id:
        return urls
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")
    return urls

def try_download_csv(urls, timeout=15):
    """Intenta descargar CSV probando varias URLs; devuelve (text, error_msg)."""
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
            # detectar HTML (login / error)
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
# Lectura robusta de archivos (CSV / XLSX / Google Sheet)
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(sheet_input: str = None, uploaded_file=None) -> pd.DataFrame:
    """
    sheet_input: URL completa o solo el sheet_id (opcional).
    uploaded_file: archivo subido por el usuario (BytesIO/FileStorage).
    """
    csv_text = None
    # 1) Si el usuario subió un archivo, priorizarlo
    if uploaded_file is not None:
        filename = getattr(uploaded_file, "name", "")
        # Si es xlsx, usar read_excel
        if filename.lower().endswith((".xls", ".xlsx")):
            try:
                # leer con header=None para detectar encabezado real
                raw = pd.read_excel(uploaded_file, header=None, engine="openpyxl")
            except Exception:
                # fallback engine
                raw = pd.read_excel(uploaded_file, header=None)
            df = _normalize_from_raw_excel(raw)
            return df
        else:
            # intentar leer como CSV (texto)
            try:
                csv_text = uploaded_file.getvalue().decode("utf-8")
            except Exception:
                csv_text = uploaded_file.getvalue().decode("latin-1")
    else:
        # 2) intentar descargar desde Google Sheets si sheet_input provisto
        if sheet_input:
            sheet_id, gid = parse_sheet_url(sheet_input)
            if not sheet_id:
                raise ValueError("No se pudo extraer el ID del Google Sheet desde la entrada proporcionada.")
            urls = build_candidate_csv_urls(sheet_id, gid)
            if not urls:
                raise ValueError("No se pudo construir una URL válida para descargar el CSV.")
            csv_text, download_error = try_download_csv(urls, timeout=15)
            if csv_text is None:
                raise ConnectionError(f"No se pudo descargar CSV: {download_error}")
        else:
            raise ValueError("No se proporcionó archivo ni URL/ID del Google Sheet.")

    # Si llegamos aquí con csv_text, parsearlo
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=0)
    except Exception:
        # intentar con header=None y normalizar
        raw = pd.read_csv(io.StringIO(csv_text), header=None)
        df = _normalize_from_raw_excel(raw)
    # Normalizar columnas y valores
    df = _ensure_expected_columns(df)
    return df

# ─────────────────────────────────────────────
# Helpers para normalizar Excel/CSV mal formateado
# ─────────────────────────────────────────────
def _normalize_from_raw_excel(raw: pd.DataFrame) -> pd.DataFrame:
    """
    raw: DataFrame leído con header=None. Buscamos la fila que contiene los encabezados
    esperados (SUSTANCIA/QUÍMICO, FAMILIA, FECHA, VIGENCIA, URL a Ficha de seguridad, PICTOGRAMA).
    Si no se encuentra, intentamos reconstruir filas leyendo en bloques.
    """
    # Convertir todo a string para facilitar búsqueda
    raw_str = raw.fillna("").astype(str)
    header_row_idx = None
    expected_tokens = [COL_SUSTANCIA.lower(), COL_FAMILIA.lower(), COL_FECHA.lower(), COL_VIGENCIA.lower()]
    for i in range(min(10, len(raw_str))):  # buscar en primeras 10 filas
        row_text = " ".join(raw_str.iloc[i].str.lower().tolist())
        if all(tok in row_text for tok in expected_tokens[:2]):  # al menos SUSTANCIA y FAMILIA
            header_row_idx = i
            break

    if header_row_idx is not None:
        # construir df con esa fila como header
        header = raw_str.iloc[header_row_idx].tolist()
        df = raw.iloc[header_row_idx + 1 :].copy()
        df.columns = [str(h).strip() if str(h).strip() != "" else f"col_{i}" for i, h in enumerate(header)]
        df = df.reset_index(drop=True)
        # limpiar columnas: quitar nombres vacíos y renombrar si detectamos tokens
        df.columns = [c.strip() for c in df.columns]
        df = _ensure_expected_columns(df)
        return df

    # Si no encontramos encabezado, intentar interpretar el archivo como bloques verticales:
    # muchas exportaciones mal hechas colocan cada registro en varias filas; intentamos agrupar por filas vacías.
    lines = []
    for r in raw_str.itertuples(index=False, name=None):
        # concatenar celdas separadas por '||' para reconstruir
        joined = "||".join([str(x).strip() for x in r if str(x).strip() != ""])
        if joined:
            lines.append(joined)
        else:
            lines.append("")  # mantener separadores

    # Agrupar bloques separados por líneas vacías
    records = []
    current = []
    for l in lines:
        if l == "":
            if current:
                records.append(current)
                current = []
        else:
            current.append(l)
    if current:
        records.append(current)

    # Cada record puede contener fields en orden: nombre, familia, fecha, vigencia, url, pictograma (o con faltantes)
    rows = []
    for rec in records:
        # rec es lista de strings; extraer elementos que parezcan URLs y números de fecha
        flat = []
        for item in rec:
            # si contiene 'http' o 'drive.google' considerarlo URL
            if "http" in item.lower():
                flat.append(item)
            else:
                # si contiene '||' fue concatenado; dividirlo
                parts = item.split("||")
                for p in parts:
                    if p.strip():
                        flat.append(p.strip())
        # heurística: buscar el primer elemento que no sea URL como nombre
        # construir fila con longitud 6 (SUSTANCIA, FAMILIA, FECHA, VIGENCIA, URL, PICTO)
        row = [""] * 6
        # asignar URL si existe
        urls = [f for f in flat if f.lower().startswith("http")]
        non_urls = [f for f in flat if not f.lower().startswith("http")]
        if non_urls:
            row[0] = non_urls[0]  # nombre
        if len(non_urls) >= 2:
            # si el segundo es una palabra corta y mayúscula, puede ser familia
            row[1] = non_urls[1]
        # buscar algo que parezca fecha (número grande excel) o 'N/A'
        for v in non_urls[2:]:
            if v.strip().upper() in ("N/A", "SIN DATO", "NA"):
                continue
            # si es número (excel serial) o contiene '/' o '-' lo tomamos como fecha
            if re.match(r"^\d{4}\.\d+$", v) or re.search(r"[/-]", v) or re.match(r"^\d{5,}$", v):
                row[2] = v
                break
        # vigencia: si aparece palabra VIGENTE/NO VIGENTE en non_urls
        for v in non_urls:
            if "vigent" in v.lower() or "vigencia" in v.lower() or v.strip().upper() in ("VIGENTE", "NO VIGENTE", "SIN DATO"):
                row[3] = v
                break
        if urls:
            row[4] = urls[0]
            if len(urls) > 1:
                row[5] = urls[1]
        rows.append(row)

    df = pd.DataFrame(rows, columns=[COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO])
    df = _ensure_expected_columns(df)
    return df

def _ensure_expected_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura que el DataFrame tenga las columnas esperadas y normaliza valores."""
    # Normalizar nombres de columnas: mapear variantes a las esperadas
    cols_map = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if "sustancia" in cl or "químico" in cl or "quimico" in cl:
            cols_map[c] = COL_SUSTANCIA
        elif "famil" in cl:
            cols_map[c] = COL_FAMILIA
        elif cl.startswith("fecha") or cl == "date":
            cols_map[c] = COL_FECHA
        elif "vigencia" in cl or "vigent" in cl:
            cols_map[c] = COL_VIGENCIA
        elif "url" in cl or "ficha" in cl or "drive" in cl:
            cols_map[c] = COL_URL
        elif "picto" in cl or "pictograma" in cl:
            cols_map[c] = COL_PICTO
    if cols_map:
        df = df.rename(columns=cols_map)

    # Añadir columnas faltantes
    for col in [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]:
        if col not in df.columns:
            df[col] = pd.NA

    # Limpiar valores
    df[COL_SUSTANCIA] = df[COL_SUSTANCIA].fillna("").astype(str).str.strip()
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("").astype(str).str.strip().replace("", "SIN FAMILIA")
    # FECHA: intentar parsear si es número (serial) o texto
    def _fmt_fecha(v):
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if s.upper() in ("N/A", "SIN DATO", ""):
            return ""
        # si parece número entero (excel serial), intentar convertir
        if re.match(r"^\d+(\.\d+)?$", s):
            try:
                # si es entero grande, puede ser excel serial; pandas to_datetime with unit='d' from 1899-12-30
                num = float(s)
                # heurística: si num > 30000 treat as excel serial
                if num > 30000:
                    dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(int(num), unit="D")
                    return dt.strftime("%d/%m/%Y")
            except Exception:
                pass
        # si contiene '/', '-' o looks like date
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
                if pd.notna(dt):
                    return dt.strftime("%d/%m/%Y")
            except Exception:
                continue
        return s

    df[COL_FECHA] = df[COL_FECHA].apply(_fmt_fecha)
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").astype(str).str.strip().str.upper()
    df[COL_URL] = df[COL_URL].fillna("").astype(str).str.strip()
    df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).str.strip()
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("SIN FAMILIA").astype(str).str.strip().str.upper()
    return df

# ─────────────────────────────────────────────
# Interfaz: entrada y subida
# ─────────────────────────────────────────────
st.title("Repositorio Hojas de Seguridad — SGA")
st.caption("Sistema Globalmente Armonizado · Kenzo Jeans · Consulta rápida de fichas de seguridad químicas")
st.divider()

with st.sidebar:
    st.header("🔎 Fuente de datos")
    st.markdown("Pega la URL completa del Google Sheet o solo el ID. Si la descarga falla, sube el archivo (XLSX o CSV).")
    sheet_input = st.text_input(
        "URL o ID del Google Sheet",
        value="https://docs.google.com/spreadsheets/d/1I06rgXcy1ACk50ApIGDVne8UbLFLClRe5wkWKT5KGAQ/edit?usp=sharing",
    )
    st.markdown("---")
    uploaded_file = st.file_uploader("Subir XLSX o CSV (opcional)", type=["xlsx", "xls", "csv"])
    if st.button("🔄 Recargar datos"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.experimental_rerun()

# ─────────────────────────────────────────────
# Cargar datos
# ─────────────────────────────────────────────
try:
    df = cargar_datos(sheet_input if sheet_input else None, uploaded_file)
except Exception as e:
    st.error(
        "❌ No se pudo leer la fuente de datos. Verifica:\n"
        "1) La URL/ID es correcta.\n"
        "2) El Sheet está compartido como 'Cualquier persona con el enlace → Lector' (si usas Google Sheets).\n"
        "3) Si subes un archivo, que sea XLSX/CSV válido."
    )
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# Sidebar: filtros y métricas
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
# Aplicar filtros
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
# Resultados
# ─────────────────────────────────────────────
n = len(df_filtrado)
if n == 0:
    st.warning("⚠️ No se encontraron fichas con los filtros aplicados.")
    st.stop()

st.markdown(f"**{n} ficha{'s' if n != 1 else ''} encontrada{'s' if n != 1 else ''}**")
st.caption("Haz clic en la tarjeta para ver el detalle completo.")

for _, row in df_filtrado.iterrows():
    nombre = str(row.get(COL_SUSTANCIA, "—")).strip() or "—"
    familia = str(row.get(COL_FAMILIA, "SIN FAMILIA")).strip() or "SIN FAMILIA"
    fecha = str(row.get(COL_FECHA, "")).strip() or "Sin fecha"
    vigencia = str(row.get(COL_VIGENCIA, "")).strip().upper() or "SIN DATO"
    url_doc = str(row.get(COL_URL, "")).strip()
    url_picto = str(row.get(COL_PICTO, "")).strip()

    es_vigente = vigencia == "VIGENTE"
    badge_cls = "badge-vigente" if es_vigente else "badge-novigente"
    badge_txt = vigencia if vigencia else "SIN DATO"

    # Mostrar tarjeta con Nombre como título y debajo las líneas solicitadas
    with st.expander(f"{'✅' if es_vigente else '⚠️'}  {nombre}", expanded=False):
        st.markdown(f'<div class="card-title">Nombre: {nombre}</div>', unsafe_allow_html=True)
        st.markdown(f"**🏭 Familia / Categoría:** {familia}")
        st.markdown(f"**📅 Última revisión:** {fecha}")
        st.markdown(f"**📄 Vigencia:** <span class=\"{badge_cls}\">{badge_txt}</span>", unsafe_allow_html=True)

        st.write("")  # espacio

        # pictograma
        if url_picto and url_picto.lower().startswith("http"):
            try:
                st.image(url_picto, caption="Pictograma SGA", width=120)
            except Exception:
                st.write("Pictograma no disponible")
        else:
            st.markdown(
                "<div style='width:90px;height:90px;border:3px solid #e53935;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2.2em;background:#fff3e0;'>⚗️</div>",
                unsafe_allow_html=True,
            )

        st.write("")

        # enlace a ficha
        if url_doc and url_doc.lower().startswith("http"):
            try:
                st.markdown(f"[📂 Abrir ficha de seguridad]({url_doc})")
            except Exception:
                st.write("Enlace no disponible")
        else:
            st.warning("🔗 Enlace no disponible")

        if not es_vigente:
            st.error("Documento **no vigente** o pendiente de actualización.")

    st.markdown("<hr style='margin:6px 0; border-color:#eceff1'>", unsafe_allow_html=True)

st.divider()
st.caption("🛡️ Kenzo Jeans – Gestión SGA · Los documentos se actualizan desde Google Sheets")
