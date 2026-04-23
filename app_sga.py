# app_sga.py
import re
import io
import requests
import streamlit as st
import pandas as pd
from typing import List, Tuple

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
# ESTILOS LIGEROS
# ─────────────────────────────────────────────
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
# COLUMNAS ESPERADAS
# ─────────────────────────────────────────────
COL_SUSTANCIA = "SUSTANCIA/QUÍMICO"
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

# ─────────────────────────────────────────────
# UTILIDADES PARA GOOGLE SHEETS
# ─────────────────────────────────────────────
def parse_sheet_url(url: str) -> Tuple[str, str]:
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

def build_candidate_csv_urls(sheet_id: str, gid: str = "0") -> List[str]:
    urls = []
    if not sheet_id:
        return urls
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}")
    urls.append(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")
    return urls

def try_download_csv(urls, timeout=15):
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
# PARSEO ROBUSTO: cuando el Excel/CSV está desalineado
# ─────────────────────────────────────────────
def _looks_like_url(s: str) -> bool:
    if not isinstance(s, str):
        return False
    s = s.strip().lower()
    return s.startswith("http") or "drive.google" in s or "docs.google" in s

def _looks_like_date_token(s: str) -> bool:
    if not isinstance(s, str):
        return False
    s = s.strip()
    # Excel serial numbers (e.g., 45390.0) or strings with / or -
    if re.match(r"^\d{4,}\.0?$", s) or re.match(r"^\d{5,}$", s):
        return True
    if re.search(r"[/-]", s):
        return True
    return False

def _flatten_dataframe_cells(df: pd.DataFrame) -> List[str]:
    """
    Devuelve una lista de celdas no vacías en orden de lectura (fila por fila),
    útil para hojas donde cada registro ocupa varias filas en una sola columna.
    """
    flat = []
    for _, row in df.iterrows():
        for val in row.tolist():
            if pd.isna(val):
                continue
            s = str(val).strip()
            if s != "":
                flat.append(s)
    return flat

def parse_flat_cells_to_records(flat: List[str]) -> pd.DataFrame:
    """
    Heurística para convertir una lista plana de celdas en registros con columnas:
    SUSTANCIA/QUÍMICO, FAMILIA, FECHA, VIGENCIA, URL a Ficha de seguridad, PICTOGRAMA
    """
    records = []
    i = 0
    while i < len(flat):
        # Buscar nombre (sustancia): preferir cadenas que no sean URL y no parezcan fecha
        name = ""
        family = ""
        fecha = ""
        vigencia = ""
        url = ""
        picto = ""

        # 1) Nombre: la primera celda que no sea URL
        if not _looks_like_url(flat[i]):
            name = flat[i]
            i += 1
        else:
            # si la celda es URL pero no hay nombre, saltarla
            i += 1
            continue

        # 2) Intentar asignar siguientes tokens a familia / fecha / vigencia / url / picto
        # Mirar hasta 6 tokens siguientes como máximo para completar el registro
        look_ahead = 0
        while i < len(flat) and look_ahead < 8:
            token = flat[i]
            if _looks_like_url(token):
                if url == "":
                    url = token
                elif picto == "":
                    picto = token
                else:
                    # si ya hay url y picto, probablemente es el inicio de la siguiente ficha
                    break
                i += 1
            elif _looks_like_date_token(token) and fecha == "":
                fecha = token
                i += 1
            elif token.strip().upper() in ("VIGENTE", "NO VIGENTE", "SIN DATO", "N/A"):
                vigencia = token
                i += 1
            else:
                # Si family está vacío y token es corto o todo mayúsculas, asignar familia
                if family == "":
                    # heurística: si token es una palabra corta o contiene 'AUX'/'GENERIC'/'PLANTA' etc.
                    if len(token.split()) <= 4 or any(k in token.upper() for k in ["AUX", "GENERIC", "PLANTA", "COLOR", "PIGMENTO", "SUAVIZ", "ENZIMAS", "REDUCTORES"]):
                        family = token
                        i += 1
                    else:
                        # si token tiene muchas palabras, puede ser parte del nombre de la sustancia (apéndice)
                        # en ese caso, si name no contiene números ni '/', lo concatenamos
                        if len(name.split()) < 6 and not _looks_like_date_token(token):
                            name = f"{name} {token}"
                            i += 1
                        else:
                            break
                else:
                    # family ya existe; si fecha vacío y token parece fecha, asignar; si no, puede ser parte del nombre siguiente
                    if fecha == "" and _looks_like_date_token(token):
                        fecha = token
                        i += 1
                    else:
                        # probablemente inicio de siguiente registro
                        break
            look_ahead += 1

        # Guardar registro si hay al menos un nombre
        if name:
            records.append({
                COL_SUSTANCIA: name.strip(),
                COL_FAMILIA: family.strip() if family else "SIN FAMILIA",
                COL_FECHA: fecha.strip(),
                COL_VIGENCIA: vigencia.strip().upper() if vigencia else "",
                COL_URL: url.strip(),
                COL_PICTO: picto.strip(),
            })
        # si no avanzó (para evitar bucle infinito), avanzar uno
        if look_ahead == 0:
            i += 1

    df = pd.DataFrame(records, columns=[COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO])
    return df

# ─────────────────────────────────────────────
# NORMALIZACIÓN FINAL
# ─────────────────────────────────────────────
def _ensure_expected_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Mapear nombres de columna variantes a los esperados
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

    # Limpiar y formatear
    df[COL_SUSTANCIA] = df[COL_SUSTANCIA].fillna("").astype(str).str.strip()
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("").astype(str).str.strip().replace("", "SIN FAMILIA")
    # FECHA: intentar convertir seriales Excel a dd/mm/YYYY
    def _fmt_fecha(v):
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if s.upper() in ("N/A", "SIN DATO", ""):
            return ""
        # excel serial heuristic
        if re.match(r"^\d+(\.0+)?$", s):
            try:
                num = int(float(s))
                if num > 30000:
                    dt = pd.to_datetime("1899-12-30") + pd.to_timedelta(num, unit="D")
                    return dt.strftime("%d/%m/%Y")
            except Exception:
                pass
        # try parse with pandas
        try:
            dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.notna(dt):
                return dt.strftime("%d/%m/%Y")
        except Exception:
            pass
        return s

    df[COL_FECHA] = df[COL_FECHA].apply(_fmt_fecha)
    df[COL_VIGENCIA] = df[COL_VIGENCIA].fillna("").astype(str).str.strip().str.upper()
    df[COL_URL] = df[COL_URL].fillna("").astype(str).str.strip()
    df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).str.strip()
    df[COL_FAMILIA] = df[COL_FAMILIA].fillna("SIN FAMILIA").astype(str).str.strip().str.upper()
    return df

# ─────────────────────────────────────────────
# LECTURA ROBUSTA DE FUENTE (Google Sheet o archivo subido)
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Cargando fichas de seguridad…")
def cargar_datos(sheet_input: str = None, uploaded_file=None) -> pd.DataFrame:
    # 1) Si el usuario subió un archivo, priorizarlo
    if uploaded_file is not None:
        filename = getattr(uploaded_file, "name", "")
        try:
            if filename.lower().endswith((".xls", ".xlsx")):
                # leer sin header para detectar encabezado real
                raw = pd.read_excel(uploaded_file, header=None, engine="openpyxl")
                # si la hoja ya tiene encabezados correctos en la primera fila, pandas puede leerlos
                # intentar detectar si la primera fila contiene los tokens esperados
                first_row = raw.iloc[0].astype(str).str.lower().tolist()
                if any("sustancia" in c for c in first_row) or any("químico" in c for c in first_row) or any("famil" in c for c in first_row):
                    # volver a leer con header=0
                    uploaded_file.seek(0)
                    df = pd.read_excel(uploaded_file, header=0, engine="openpyxl")
                    df = _ensure_expected_columns(df)
                    return df
                else:
                    # normalizar desde raw
                    df = _normalize_from_raw_excel(raw)
                    df = _ensure_expected_columns(df)
                    return df
            else:
                # CSV: intentar leer con header=0; si falla, leer sin header y normalizar
                try:
                    uploaded_file.seek(0)
                    csv_text = uploaded_file.getvalue().decode("utf-8")
                except Exception:
                    uploaded_file.seek(0)
                    csv_text = uploaded_file.getvalue().decode("latin-1")
                try:
                    df = pd.read_csv(io.StringIO(csv_text), header=0)
                    df = _ensure_expected_columns(df)
                    # if df has very few columns and many rows with single values, flatten
                    non_empty_cols = df.dropna(how="all", axis=1).shape[1]
                    if non_empty_cols <= 1:
                        flat = _flatten_dataframe_cells(df)
                        df = parse_flat_cells_to_records(flat)
                        df = _ensure_expected_columns(df)
                    return df
                except Exception:
                    raw = pd.read_csv(io.StringIO(csv_text), header=None)
                    flat = _flatten_dataframe_cells(raw)
                    df = parse_flat_cells_to_records(flat)
                    df = _ensure_expected_columns(df)
                    return df
        except Exception as e:
            raise RuntimeError(f"Error leyendo el archivo subido: {e}")

    # 2) Si no hay archivo, intentar descargar desde Google Sheets
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
        # intentar parsear CSV con header=0
        try:
            df = pd.read_csv(io.StringIO(csv_text), header=0)
            df = _ensure_expected_columns(df)
            non_empty_cols = df.dropna(how="all", axis=1).shape[1]
            if non_empty_cols <= 1:
                flat = _flatten_dataframe_cells(df)
                df = parse_flat_cells_to_records(flat)
                df = _ensure_expected_columns(df)
            return df
        except Exception:
            raw = pd.read_csv(io.StringIO(csv_text), header=None)
            flat = _flatten_dataframe_cells(raw)
            df = parse_flat_cells_to_records(flat)
            df = _ensure_expected_columns(df)
            return df

    raise ValueError("No se proporcionó archivo ni URL/ID del Google Sheet.")

# Helper reutilizable para normalizar raw excel (header=None)
def _normalize_from_raw_excel(raw: pd.DataFrame) -> pd.DataFrame:
    # Convertir todo a string para búsqueda
    raw_str = raw.fillna("").astype(str)
    header_row_idx = None
    expected_tokens = [COL_SUSTANCIA.lower(), COL_FAMILIA.lower(), COL_FECHA.lower(), COL_VIGENCIA.lower()]
    for i in range(min(10, len(raw_str))):
        row_text = " ".join(raw_str.iloc[i].str.lower().tolist())
        if any("sustancia" in row_text or "químico" in row_text for _ in (0,)) and ("famil" in row_text or "familia" in row_text):
            header_row_idx = i
            break
    if header_row_idx is not None:
        header = raw_str.iloc[header_row_idx].tolist()
        df = raw.iloc[header_row_idx + 1 :].copy()
        df.columns = [str(h).strip() if str(h).strip() != "" else f"col_{i}" for i, h in enumerate(header)]
        df = df.reset_index(drop=True)
        df = _ensure_expected_columns(df)
        return df
    # Si no se detecta encabezado, aplanar y parsear
    flat = _flatten_dataframe_cells(raw)
    df = parse_flat_cells_to_records(flat)
    df = _ensure_expected_columns(df)
    return df

# ─────────────────────────────────────────────
# INTERFAZ: entrada y subida
# ─────────────────────────────────────────────
st.title("Repositorio Hojas de Seguridad — SGA")
st.caption("Sistema Globalmente Armonizado · Kenzo Jeans · Consulta rápida de fichas de seguridad químicas")
st.divider()

with st.sidebar:
    st.header("🔎 Fuente de datos")
    st.markdown("Pega la URL completa del Google Sheet o solo el ID. Si la descarga falla, sube el archivo (XLSX/CSV).")
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
# CARGAR DATOS
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

    with st.expander(f"{'✅' if es_vigente else '⚠️'}  {nombre}", expanded=False):
        st.markdown(f'<div class="card-title">Nombre: {nombre}</div>', unsafe_allow_html=True)
        st.markdown(f"**🏭 Familia / Categoría:** {familia}")
        st.markdown(f"**📅 Última revisión:** {fecha}")
        st.markdown(f"**📄 Vigencia:** <span class=\"{badge_cls}\">{badge_txt}</span>", unsafe_allow_html=True)

        st.write("")

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

        if url_doc and url_doc.lower().startswith("http"):
            st.markdown(f"[📂 Abrir ficha de seguridad]({url_doc})")
        else:
            st.warning("🔗 Enlace no disponible")

        if not es_vigente:
            st.error("Documento **no vigente** o pendiente de actualización.")

    st.markdown("<hr style='margin:6px 0; border-color:#eceff1'>", unsafe_allow_html=True)

st.divider()
st.caption("🛡️ Kenzo Jeans – Gestión SGA · Los documentos se actualizan desde Google Sheets")
