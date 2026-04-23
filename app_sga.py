# app_sga.py
import re
import io
import requests
import streamlit as st
import pandas as pd
from typing import Optional, Tuple, List

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="📄 Repositorio Hojas de Seguridad (SGA) – Kenzo Jeans",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
.card-title { font-size:1.05rem; font-weight:700; margin:0 0 6px 0; }
.detail-label { font-weight:700; color:#263238; }
.badge-vigente { background:#e8f5e9; color:#2e7d32; border-radius:12px; padding:4px 10px; font-weight:700; }
.badge-novigente { background:#ffebee; color:#c62828; border-radius:12px; padding:4px 10px; font-weight:700; }
.debug { font-size:0.85rem; color:#666; }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# COLUMNAS ESPERADAS
# ─────────────────────────────────────────────
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA = "FAMILIA"
COL_FECHA = "FECHA"
COL_VIGENCIA = "VIGENCIA"
COL_URL = "URL a Ficha de seguridad"
COL_PICTO = "PICTOGRAMA"

EXPECTED_HEADERS = [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]

# ─────────────────────────────────────────────
# UTILIDADES: Google Sheets y descarga CSV
# ─────────────────────────────────────────────
def parse_sheet_url(url: str) -> Tuple[Optional[str], str]:
    if not url or not isinstance(url, str):
        return None, "0"
    s = url.strip()
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", s)
    sheet_id = m.group(1) if m else None
    if not sheet_id and re.fullmatch(r"[a-zA-Z0-9-_]+", s):
        sheet_id = s
    m_gid = re.search(r"[?&]gid=(\d+)", s) or re.search(r"#gid=(\d+)", s)
    gid = m_gid.group(1) if m_gid else "0"
    return sheet_id, gid

def build_csv_urls(sheet_id: str, gid: str = "0") -> List[str]:
    urls = []
    if not sheet_id:
        return urls
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")
    return urls

def try_download_csv(urls, timeout=15):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0)", "Accept": "text/csv, */*; q=0.1"}
    last_err = None
    for u in urls:
        try:
            resp = requests.get(u, headers=headers, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            text = resp.text
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
# DETECCIÓN DE ENCABEZADO ROBUSTA
# ─────────────────────────────────────────────
def find_header_row(df: pd.DataFrame, expected_tokens=EXPECTED_HEADERS, search_rows: int = 30) -> Optional[int]:
    df_str = df.fillna("").astype(str)
    expected_lower = [t.lower() for t in expected_tokens]
    max_rows = min(search_rows, len(df_str))
    for i in range(max_rows):
        row = df_str.iloc[i].astype(str).str.lower().tolist()
        count = 0
        for token in expected_lower:
            for cell in row:
                if token in cell:
                    count += 1
                    break
        if count >= 2:
            return i
    for i in range(max_rows):
        row = df_str.iloc[i].astype(str).str.lower().tolist()
        if any("sustancia" in c or "químico" in c or "quimico" in c for c in row):
            return i
    return None

def read_with_detected_header_from_csv_text(csv_text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)
    header_idx = find_header_row(raw, EXPECTED_HEADERS, search_rows=30)
    if header_idx is not None:
        header = raw.iloc[header_idx].astype(str).tolist()
        df = raw.iloc[header_idx + 1 :].copy().reset_index(drop=True)
        df.columns = [str(h).strip() if str(h).strip() != "" else f"col_{i}" for i, h in enumerate(header)]
    else:
        try:
            df = pd.read_csv(io.StringIO(csv_text), header=0, dtype=str)
        except Exception:
            df = raw.copy()
            df.columns = [f"col_{i}" for i in range(df.shape[1])]
    df = ensure_expected_columns(df)
    return df

def read_excel_with_detected_header(uploaded_file) -> pd.DataFrame:
    raw = pd.read_excel(uploaded_file, header=None, dtype=str, engine="openpyxl")
    header_idx = find_header_row(raw, EXPECTED_HEADERS, search_rows=30)
    if header_idx is not None:
        header = raw.iloc[header_idx].astype(str).tolist()
        df = raw.iloc[header_idx + 1 :].copy().reset_index(drop=True)
        df.columns = [str(h).strip() if str(h).strip() != "" else f"col_{i}" for i, h in enumerate(header)]
    else:
        uploaded_file.seek(0)
        try:
            df = pd.read_excel(uploaded_file, header=0, dtype=str, engine="openpyxl")
        except Exception:
            df = raw.copy()
            df.columns = [f"col_{i}" for i in range(df.shape[1])]
    df = ensure_expected_columns(df)
    return df

# ─────────────────────────────────────────────
# NORMALIZACIÓN DE VIGENCIA
# ─────────────────────────────────────────────
def normalize_vigencia(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip().upper()
    if s in ("", "N/A", "NA", "SIN DATO", "SIN_DATO", "ND"):
        return ""
    s_clean = re.sub(r"[^A-ZÑÁÉÍÓÚ0-9\s\-_/]", "", s)
    s_clean = re.sub(r"[-_/]+", " ", s_clean).strip()
    if "NO" in s_clean and ("VIGENT" in s_clean or "VIGEN" in s_clean or "VIGENCIA" in s_clean or "VIGENTE" in s_clean):
        return "NO VIGENTE"
    if "VIGENT" in s_clean or "VIGEN" in s_clean or "VIGENTE" in s_clean:
        return "VIGENTE"
    if s_clean.startswith("NO "):
        return "NO VIGENTE"
    if s_clean in ("SI", "S", "YES"):
        return "VIGENTE"
    if "VIG" in s_clean:
        if "NO" in s_clean:
            return "NO VIGENTE"
        return "VIGENTE"
    return ""

# ─────────────────────────────────────────────
# NORMALIZACIÓN DE COLUMNAS Y FECHAS
# ─────────────────────────────────────────────
def ensure_expected_columns(df: pd.DataFrame) -> pd.DataFrame:
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

    for col in EXPECTED_HEADERS:
        if col not in df.columns:
            df[col] = pd.NA

    # Forzar strings para evitar conversiones a booleano
    for col in EXPECTED_HEADERS:
        df[col] = df[col].astype(str).fillna("").replace("nan", "")

    # Familia: evitar booleanos y normalizar
    df[COL_FAMILIA] = df[COL_FAMILIA].apply(lambda x: x.strip() if x and x.strip().upper() not in ("NAN", "NONE", "FALSE", "TRUE") else "")
    df[COL_FAMILIA] = df[COL_FAMILIA].replace("", "SIN FAMILIA").str.upper()

    # Fecha: convertir seriales Excel y formatos comunes
    def fmt_fecha(v):
        if not v or str(v).strip().upper() in ("N/A", "SIN DATO", ""):
            return ""
        s = str(v).strip()
        if re.match(r"^\d+(\.0+)?$", s):
            try:
                num = int(float(s))
                if num > 30000:
                    dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(num, unit="D")
                    return dt.strftime("%d/%m/%Y")
            except Exception:
                pass
        try:
            dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.notna(dt):
                return dt.strftime("%d/%m/%Y")
        except Exception:
            pass
        return s

    df[COL_FECHA] = df[COL_FECHA].apply(fmt_fecha)
    df[COL_VIGENCIA] = df[COL_VIGENCIA].apply(normalize_vigencia)
    df[COL_URL] = df[COL_URL].apply(lambda x: x.strip() if x and x.strip().lower() != "nan" else "")
    df[COL_PICTO] = df[COL_PICTO].apply(lambda x: x.strip() if x and x.strip().lower() != "nan" else "")
    return df

# ─────────────────────────────────────────────
# NORMALIZAR ENLACES DE GOOGLE DRIVE (para mostrar imágenes)
# ─────────────────────────────────────────────
def normalize_drive_variants(url: str) -> List[str]:
    if not isinstance(url, str) or not url.strip():
        return []
    u = url.strip()
    candidates = [u]
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", u)
    if m:
        fid = m.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
            f"https://drive.google.com/thumbnail?id={fid}",
        ]
    m2 = re.search(r"open\?id=([a-zA-Z0-9_-]+)", u)
    if m2:
        fid = m2.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
        ]
    m3 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", u)
    if m3:
        fid = m3.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
        ]
    seen = set(); out = []
    for c in candidates:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def is_image_content_type(content_type: Optional[str]) -> bool:
    if not content_type:
        return False
    return content_type.lower().startswith("image/")

def probe_image_url(url: str, timeout: int = 6):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0)"}
    try:
        resp = requests.head(url, headers=headers, allow_redirects=True, timeout=5)
        status = resp.status_code
        ctype = resp.headers.get("Content-Type", "")
        if resp.ok and ctype and is_image_content_type(ctype):
            g = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
            g.raise_for_status()
            return True, g.content, g.status_code, g.headers.get("Content-Type", "")
        g = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
        status = g.status_code
        ctype = g.headers.get("Content-Type", "")
        if g.ok and ctype and is_image_content_type(ctype):
            return True, g.content, status, ctype
        return False, None, status, ctype
    except requests.RequestException as e:
        return False, None, None, str(e)

# ─────────────────────────────────────────────
# LECTURA ROBUSTA DE FUENTE (Google Sheet o archivo subido)
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(sheet_input: Optional[str] = None, uploaded_file=None) -> pd.DataFrame:
    """
    Si no se proporciona ni archivo ni sheet_input, devuelve un DataFrame vacío
    con las columnas esperadas (no lanza excepción). Esto evita errores al pulsar
    recargar sin entrada.
    """
    # 1) archivo subido
    if uploaded_file is not None:
        filename = getattr(uploaded_file, "name", "").lower()
        if filename.endswith((".xls", ".xlsx")):
            uploaded_file.seek(0)
            return read_excel_with_detected_header(uploaded_file)
        else:
            uploaded_file.seek(0)
            try:
                text = uploaded_file.getvalue().decode("utf-8")
            except Exception:
                uploaded_file.seek(0)
                text = uploaded_file.getvalue().decode("latin-1")
            return read_with_detected_header_from_csv_text(text)

    # 2) Google Sheet
    if sheet_input:
        sheet_id, gid = parse_sheet_url(sheet_input)
        if not sheet_id:
            raise ValueError("No se pudo extraer el ID del Google Sheet desde la entrada proporcionada.")
        urls = build_csv_urls(sheet_id, gid)
        if not urls:
            raise ValueError("No se pudo construir una URL válida para descargar el CSV.")
        csv_text, err = try_download_csv(urls, timeout=15)
        if csv_text is None:
            raise ConnectionError(f"No se pudo descargar CSV: {err}")
        return read_with_detected_header_from_csv_text(csv_text)

    # Si no hay entrada, devolver DataFrame vacío con columnas esperadas
    empty = pd.DataFrame(columns=EXPECTED_HEADERS)
    empty = ensure_expected_columns(empty)
    return empty

# ─────────────────────────────────────────────
# INTERFAZ: entrada y subida
# ─────────────────────────────────────────────
st.title("Repositorio Hojas de Seguridad — SGA")
st.caption("Sistema Globalmente Armonizado · Kenzo Jeans · Consulta rápida de fichas de seguridad químicas")
st.divider()

with st.sidebar:
    st.header("🔎 Fuente de datos")
    st.markdown("Pega la URL completa del Google Sheet o sube el archivo (XLSX/CSV).")
    sheet_input = st.text_input("URL o ID del Google Sheet", value="")
    uploaded_file = st.file_uploader("Subir XLSX o CSV (opcional)", type=["xlsx", "xls", "csv"])
    if st.button("🔄 Recargar datos"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

# ─────────────────────────────────────────────
# CARGAR DATOS
# ─────────────────────────────────────────────
try:
    df = cargar_datos(sheet_input if sheet_input else None, uploaded_file)
except Exception as e:
    st.error(
        "❌ No se pudo leer la fuente de datos. Verifica:\n"
        "1) La URL/ID es correcta.\n"
        "2) El Sheet esté compartido como 'Cualquier persona con el enlace → Lector'.\n"
        "3) Si subes un archivo, que sea XLSX/CSV válido."
    )
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# Normalizar columnas y preparar datos
# ─────────────────────────────────────────────
df.columns = [c.strip() for c in df.columns]
df = ensure_expected_columns(df)

# ─────────────────────────────────────────────
# Si no hay datos, mostrar mensaje y permitir al usuario subir o pegar
# ─────────────────────────────────────────────
if df.empty or (len(df) == 0):
    st.info("No se han cargado fichas todavía. Sube un archivo XLSX/CSV o pega la URL/ID del Google Sheet en la barra lateral.")
    st.stop()

# ─────────────────────────────────────────────
# DEBUG OPCIONAL: mostrar primeras filas y URLs de pictogramas
# ─────────────────────────────────────────────
debug = st.sidebar.checkbox("Mostrar diagnóstico (URLs pictograma y primeras filas)", value=False)
if debug:
    st.sidebar.markdown("**Primeras filas (normalizadas)**")
    st.sidebar.dataframe(df[[COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_PICTO]].head(20))
    st.sidebar.markdown("**Ejemplo de URLs de pictograma**")
    sample_urls = [u for u in df[COL_PICTO].unique().tolist() if u][:10]
    for u in sample_urls:
        st.sidebar.text(u)

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
# RESULTADOS: mostrar Nombre como título y detalles debajo
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
    url_picto_raw = str(row.get(COL_PICTO, "")).strip()

    es_vigente = vigencia == "VIGENTE"
    badge_cls = "badge-vigente" if es_vigente else "badge-novigente"
    badge_txt = vigencia if vigencia else "SIN DATO"

    with st.expander(f"{'✅' if es_vigente else '⚠️'}  {nombre}", expanded=False):
        st.markdown(f'<div class="card-title">Nombre: {nombre}</div>', unsafe_allow_html=True)
        st.markdown(f"**🏭 Familia / Categoría:** {familia}")
        st.markdown(f"**📅 Última revisión:** {fecha}")
        st.markdown(f"**📄 Vigencia:** <span class=\"{badge_cls}\">{badge_txt}</span>", unsafe_allow_html=True)
        st.write("")

        # Mostrar pictograma: probar variantes de Drive y fallback a bytes
        shown = False
        if url_picto_raw:
            variants = normalize_drive_variants(url_picto_raw)
            if url_picto_raw not in variants:
                variants.append(url_picto_raw)
            for v in variants:
                # 1) intentar st.image(v) directo
                try:
                    st.image(v, caption="Pictograma SGA", width=120)
                    shown = True
                    break
                except Exception:
                    # 2) intentar descargar bytes y mostrar
                    ok, img_bytes, status, ctype = probe_image_url(v)
                    if ok and img_bytes:
                        try:
                            st.image(img_bytes, caption="Pictograma SGA", width=120)
                            shown = True
                            break
                        except Exception:
                            shown = False
                    # continuar con la siguiente variante
            if not shown:
                st.write("⚗️ Pictograma no disponible. Posibles causas: enlace no público, Drive requiere autenticación, o la URL no apunta a una imagen.")
                if debug:
                    st.write("Variantes probadas:", variants)
        else:
            st.markdown(
                "<div style='width:90px;height:90px;border:3px solid #e53935;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2.2em;background:#fff3e0;'>⚗️</div>",
                unsafe_allow_html=True,
            )

        st.write("")
        if url_doc and url_doc.lower().startswith("http"):
            st.markdown(f"[📂 Abrir ficha de seguridad]({url_doc})")
        else:
            st.warning("🔗 Enlace no disponible")

        if not es_vigente:
            st.error("Documento **no vigente** o pendiente de actualización.")

    st.markdown("<hr style='margin:6px 0; border-color:#eceff1'>", unsafe_allow_html=True)

st.divider()
st.caption("🛡️ Kenzo Jeans – Gestión SGA · Los documentos se actualizan desde Google Sheets")
