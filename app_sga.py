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
    page_title="📄Repositorio Hojas de Seguridad (SGA) – Kenzo Jeans",
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
COL_FAMILIA   = "FAMILIA"
COL_FECHA     = "FECHA"
COL_VIGENCIA  = "VIGENCIA"
COL_URL       = "URL a Ficha de seguridad"
COL_PICTO     = "PICTOGRAMA"

EXPECTED_HEADERS = [COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_URL, COL_PICTO]

# ─────────────────────────────────────────────
# UTILIDADES: normalización y descarga
# ─────────────────────────────────────────────
def normalize_drive_variants(url: str) -> List[str]:
    """
    Genera variantes de URL para Google Drive y devuelve lista de URLs candidatas.
    """
    if not isinstance(url, str) or not url.strip():
        return []
    u = url.strip()
    candidates = [u]

    # si contiene /d/FILE_ID/
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", u)
    if m:
        fid = m.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
            f"https://drive.google.com/thumbnail?id={fid}",
        ]

    # open?id=FILE_ID
    m2 = re.search(r"open\?id=([a-zA-Z0-9_-]+)", u)
    if m2:
        fid = m2.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
        ]

    # share link with id= in query
    m3 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", u)
    if m3:
        fid = m3.group(1)
        candidates += [
            f"https://drive.google.com/uc?export=view&id={fid}",
            f"https://drive.google.com/uc?export=download&id={fid}",
        ]

    # eliminar duplicados manteniendo orden
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out

def is_image_content_type(content_type: Optional[str]) -> bool:
    if not content_type:
        return False
    return content_type.lower().startswith("image/")

def try_fetch_image_bytes(url: str, timeout: int = 8) -> Tuple[Optional[bytes], Optional[int], Optional[str]]:
    """
    Intenta descargar la URL y devuelve (bytes or None, status_code or None, content_type or None).
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        status = resp.status_code
        ctype = resp.headers.get("Content-Type", "")
        if resp.ok and is_image_content_type(ctype):
            return resp.content, status, ctype
        # si no es imagen, devolver None pero con status y ctype para diagnóstico
        return None, status, ctype
    except requests.RequestException as e:
        return None, None, str(e)

# ─────────────────────────────────────────────
# LECTURA Y NORMALIZACIÓN DE DATOS (simplificada)
# ─────────────────────────────────────────────
def ensure_expected_columns(df: pd.DataFrame) -> pd.DataFrame:
    # renombrar columnas si hay variantes
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

    # asegurar columnas
    for col in EXPECTED_HEADERS:
        if col not in df.columns:
            df[col] = ""

    # forzar strings para evitar booleanos
    for col in EXPECTED_HEADERS:
        df[col] = df[col].astype(str).fillna("").replace("nan", "")

    # normalizar familia
    df[COL_FAMILIA] = df[COL_FAMILIA].apply(lambda x: x.strip().upper() if x.strip() else "SIN FAMILIA")

    # normalizar vigencia (simple)
    df[COL_VIGENCIA] = df[COL_VIGENCIA].astype(str).str.strip().str.upper().replace({"N/A": "", "NONE": ""})

    # fecha: si es número excel, convertir a dd/mm/YYYY
    def fmt_fecha(v):
        s = str(v).strip()
        if not s or s.upper() in ("N/A", "NONE"):
            return ""
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
    return df

# ─────────────────────────────────────────────
# INTERFAZ: entrada y subida
# ─────────────────────────────────────────────
st.title("Repositorio Hojas de Seguridad — SGA")
st.caption("Sistema Globalmente Armonizado · Kenzo Jeans")
st.divider()

with st.sidebar:
    st.header("Fuente de datos")
    st.markdown("Pega la URL del Google Sheet o sube un archivo (XLSX/CSV).")
    sheet_input = st.text_input("URL o ID del Google Sheet", value="")
    uploaded_file = st.file_uploader("Subir XLSX o CSV (opcional)", type=["xlsx", "xls", "csv"])
    debug = st.checkbox("Mostrar diagnóstico de pictogramas", value=False)
    if st.button("🔄 Recargar datos"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

# ─────────────────────────────────────────────
# CARGAR DATOS: prioriza archivo subido
# ─────────────────────────────────────────────
def load_df_from_uploaded(uploaded) -> pd.DataFrame:
    name = getattr(uploaded, "name", "").lower()
    if name.endswith((".xls", ".xlsx")):
        uploaded.seek(0)
        df = pd.read_excel(uploaded, dtype=str, engine="openpyxl")
    else:
        uploaded.seek(0)
        try:
            text = uploaded.getvalue().decode("utf-8")
        except Exception:
            text = uploaded.getvalue().decode("latin-1")
        df = pd.read_csv(io.StringIO(text), dtype=str)
    return df

def load_df_from_sheet_url(sheet_url: str) -> pd.DataFrame:
    # extraer id si es posible
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    sheet_id = m.group(1) if m else (sheet_url if re.fullmatch(r"[a-zA-Z0-9-_]+", sheet_url) else None)
    if not sheet_id:
        raise ValueError("No se pudo extraer ID del Google Sheet.")
    gid = "0"
    m_gid = re.search(r"[?&]gid=(\d+)", sheet_url) or re.search(r"#gid=(\d+)", sheet_url)
    if m_gid:
        gid = m_gid.group(1)
    urls = [
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}",
    ]
    # intentar descargar
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SGA-App/1.0)"}
    last_err = None
    for u in urls:
        try:
            resp = requests.get(u, headers=headers, timeout=15)
            resp.raise_for_status()
            text = resp.text
            # si devuelve HTML, fallar
            if text.strip().lower().startswith("<!doctype html"):
                last_err = f"Respuesta HTML desde {u}"
                continue
            df = pd.read_csv(io.StringIO(text), dtype=str, header=0)
            return df
        except Exception as e:
            last_err = str(e)
    raise ConnectionError(f"No se pudo descargar CSV: {last_err}")

# cargar df
try:
    if uploaded_file is not None:
        df = load_df_from_uploaded(uploaded_file)
    elif sheet_input:
        df = load_df_from_sheet_url(sheet_input)
    else:
        st.info("Sube un archivo o pega la URL del Google Sheet para cargar datos.")
        st.stop()
except Exception as e:
    st.error("Error cargando datos: " + str(e))
    st.stop()

# normalizar columnas y valores
df.columns = [str(c).strip() for c in df.columns]
df = ensure_expected_columns(df)

# normalizar pictograma URLs (variantes de Drive)
df[COL_PICTO] = df[COL_PICTO].fillna("").astype(str).apply(lambda u: u.strip())

# ─────────────────────────────────────────────
# DIAGNÓSTICO: mostrar URLs y estado si el usuario lo activa
# ─────────────────────────────────────────────
if debug:
    st.sidebar.markdown("**Primeras filas (normalizadas)**")
    st.sidebar.dataframe(df[[COL_SUSTANCIA, COL_FAMILIA, COL_FECHA, COL_VIGENCIA, COL_PICTO]].head(20))
    st.sidebar.markdown("**Comprobación rápida de URLs de pictograma (primeras 10 no vacías)**")
    sample_urls = [u for u in df[COL_PICTO].unique().tolist() if u][:10]
    for u in sample_urls:
        st.sidebar.markdown(f"- {u}")
        # probar variantes de Drive
        variants = normalize_drive_variants(u)
        for v in variants:
            img_bytes, status, ctype = try_fetch_image_bytes(v, timeout=6)
            st.sidebar.markdown(f"  - {v} → status: {status} ; content-type: {ctype} ; image_ok: {bool(img_bytes)}")

# ─────────────────────────────────────────────
# SIDEBAR: filtros y métricas
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")
    busqueda = st.text_input("Buscar sustancia", placeholder="Ej: ÁCIDO OXÁLICO")
    familias_disponibles = sorted(df[COL_FAMILIA].replace("", "SIN FAMILIA").unique().tolist())
    familias_sel = st.multiselect("Familia / categoría", options=familias_disponibles, default=[])
    estado_sel = st.radio("Estado de vigencia", options=["Todos", "✅ Vigentes", "⚠️ No vigentes"], index=0)

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_filtrado = df.copy()
if busqueda and busqueda.strip():
    df_filtrado = df_filtrado[df_filtrado[COL_SUSTANCIA].str.contains(busqueda.strip(), case=False, na=False)]
if familias_sel:
    df_filtrado = df_filtrado[df_filtrado[COL_FAMILIA].isin(familias_sel)]
if estado_sel == "✅ Vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] == "VIGENTE"]
elif estado_sel == "⚠️ No vigentes":
    df_filtrado = df_filtrado[df_filtrado[COL_VIGENCIA] != "VIGENTE"]

# ─────────────────────────────────────────────
# RESULTADOS: mostrar Nombre y detalles; mostrar pictograma con varios intentos
# ─────────────────────────────────────────────
n = len(df_filtrado)
if n == 0:
    st.warning("⚠️ No se encontraron fichas con los filtros aplicados.")
    st.stop()

st.markdown(f"**{n} ficha{'s' if n != 1 else ''} encontrada{'s' if n != 1 else ''}**")
st.caption("Haz clic en la tarjeta para ver el detalle completo.")

for _, row in df_filtrado.iterrows():
    nombre = str(row.get(COL_SUSTANCIA, "")).strip() or "—"
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

        # Mostrar pictograma: probar variantes de Drive y fallback a descarga de bytes
        shown = False
        if url_picto_raw:
            variants = normalize_drive_variants(url_picto_raw)
            # añadir la URL original al final si no está
            if url_picto_raw not in variants:
                variants.append(url_picto_raw)
            for v in variants:
                # 1) intentar st.image(v) directo (rápido)
                try:
                    st.image(v, caption="Pictograma SGA", width=120)
                    shown = True
                    break
                except Exception:
                    # 2) intentar descargar bytes y mostrar
                    img_bytes, status, ctype = try_fetch_image_bytes(v, timeout=6)
                    if img_bytes:
                        try:
                            st.image(img_bytes, caption="Pictograma SGA", width=120)
                            shown = True
                            break
                        except Exception:
                            shown = False
                    # si no hay bytes, continuar con la siguiente variante
            if not shown:
                st.write("⚗️ Pictograma no disponible. Posibles causas: enlace no público, Google Drive requiere autenticación, o la URL no apunta a una imagen.")
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
