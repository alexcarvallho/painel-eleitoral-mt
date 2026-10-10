from pathlib import Path
import base64
import html
import io
import math
import re
import unicodedata
from difflib import get_close_matches
from datetime import datetime

import polars as pl
import pandas as pd
import plotly.express as px
import shapefile
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    from reportlab.pdfgen.canvas import FILL_EVEN_ODD
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

BASE = Path(__file__).resolve().parent.parent
DADOS = BASE / "dados"
PARQUET = DADOS / "votacao_mt.parquet"
FOTOS = DADOS / "candidatos"
ARQUIVO_MAPA = DADOS / "mapa_mt" / "MT_Municipios_2025.shp"

TOTAL_MUNICIPIOS_MT = 142
TOP_RANKING = 15

st.set_page_config(
    page_title="Painel Eleitoral MT | Alex Flavio Junior de Carvalho",
    page_icon="🗳️",
    layout="wide"
)

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(128,128,128,0.25);
}
[data-testid="stSidebar"] h1 { font-size: 1.35rem; letter-spacing: -0.3px; }

/* ---------- Assinatura profissional na barra lateral ---------- */
.sidebar-author {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 10px 16px 10px; margin: 0 0 14px 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.sidebar-author-icon {
    width: 44px; height: 44px; flex: 0 0 44px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%; background: #303653; color: #ffffff;
}
.sidebar-author-copy { min-width: 0; }
.sidebar-author-label {
    color: #cbd5e1; font-size: 10px; line-height: 1.4;
    font-weight: 700; letter-spacing: 0.055em; margin-bottom: 4px;
}
.sidebar-author-name {
    color: #f8fafc; font-size: 14px;
    line-height: 1.35; font-weight: 750; overflow-wrap: anywhere;
    margin-bottom: 5px;
}
.sidebar-author-sub {
    color: #c7d2fe; font-size: 11px; line-height: 1.4;
}

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    opacity: 0.7;
    font-weight: 600;
}
[data-baseweb="select"] > div { border-radius: 10px; }

/* ---------- Cabeçalho ---------- */
.chip {
    display: inline-block;
    padding: 3px 11px;
    margin: 4px 6px 0 0;
    border-radius: 99px;
    font-size: 12px;
    background: rgba(99,102,241,0.15);
    color: #818cf8;
    font-weight: 600;
}

/* ---------- Cartão do candidato (hero) ---------- */
.hero {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    padding: 20px 22px;
    border-radius: 20px;
    color: #fff;
    background: linear-gradient(120deg, #4f46e5, #06b6d4);
    box-shadow: 0 10px 28px rgba(79,70,229,0.25);
    min-height: 120px;
}
.hero-foto, .hero-foto-vazia {
    width: 92px; height: 92px; flex: 0 0 92px;
    border-radius: 50%;
    border: 4px solid #ffffff;
    background: #ffffff;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
}
.hero-foto { object-fit: cover; object-position: center top; background: #ffffff; border: 4px solid #ffffff; box-sizing: border-box; }
.hero-foto-vazia {
    display: flex; align-items: center; justify-content: center;
    font-size: 30px; font-weight: 800;
    background: #ffffff;
    color: #4f46e5;
}
.hero-info { flex: 1 1 200px; min-width: 0; }
.hero-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.85; }
.hero-nome { font-size: 22px; font-weight: 800; line-height: 1.2; overflow-wrap: anywhere; margin: 2px 0; }
.hero-sub { font-size: 13px; opacity: 0.92; }
.hero-votos { text-align: right; margin-left: auto; }
.hero-total { font-size: 34px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.1; }

/* ---------- KPIs ---------- */
.kpi {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 16px;
    padding: 14px 16px;
    background: var(--secondary-background-color, rgba(128,128,128,0.08));
    height: 100%;
}
.kpi-l { font-size: 12px; opacity: 0.65; }
.kpi-v { font-size: 24px; font-weight: 800; letter-spacing: -0.4px; margin: 3px 0; overflow-wrap: anywhere; }
.kpi-d { font-size: 12px; color: #22c55e; }

/* ---------- Ranking em barras ---------- */
.rk-box {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 16px;
    padding: 14px 16px;
    background: var(--secondary-background-color, rgba(128,128,128,0.08));
}
.rk-row { display: grid; grid-template-columns: 26px 1fr 92px; gap: 10px; align-items: center; margin: 9px 0; }
.rk-pos { font-size: 12px; opacity: 0.55; font-weight: 700; text-align: center; }
.rk-nome { font-size: 13px; font-weight: 600; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rk-bar { height: 8px; border-radius: 9px; background: rgba(128,128,128,0.18); overflow: hidden; }
.rk-bar i { display: block; height: 100%; border-radius: 9px; background: linear-gradient(90deg, #6366f1, #06b6d4); }
.rk-val { text-align: right; font-size: 13px; }
.rk-val b { display: block; font-size: 14px; }
.rk-val span { font-size: 11px; opacity: 0.65; }

/* ---------- Insights ---------- */
.insight {
    border: 1px solid rgba(128,128,128,0.25);
    border-left: 4px solid #6366f1;
    border-radius: 14px;
    padding: 14px 16px;
    background: var(--secondary-background-color, rgba(128,128,128,0.08));
    height: 100%;
    font-size: 14px;
    line-height: 1.5;
}
.insight b { display: block; margin-bottom: 4px; }

/* ---------- Layout híbrido: computador, tablet e celular ---------- */
@media (max-width: 900px) {
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1.25rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .hero {
        gap: 12px;
        padding: 16px;
        border-radius: 16px;
    }
    .hero-foto, .hero-foto-vazia {
        width: 70px;
        height: 70px;
        flex-basis: 70px;
    }
    .hero-nome { font-size: 19px; }
    .hero-votos {
        flex: 1 1 100%;
        margin-left: 82px;
        text-align: left;
    }
    .hero-total { font-size: 28px; }
    .kpi { padding: 12px; }
    .kpi-v { font-size: 20px; }
    .rk-box { padding: 12px; }
    .rk-row { grid-template-columns: 22px minmax(0, 1fr) 82px; gap: 7px; }
    .rk-nome { font-size: 12px; }
    .rk-val { font-size: 12px; }
    .rk-val b { font-size: 13px; }
}
@media (max-width: 600px) {
    .block-container {
        padding-top: 0.75rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
    }
    h1 { font-size: 1.55rem !important; line-height: 1.2 !important; }
    h2 { font-size: 1.25rem !important; line-height: 1.25 !important; }
    h3 { font-size: 1.05rem !important; }
    .chip { font-size: 10px; padding: 4px 8px; margin-right: 3px; }
    .hero { gap: 10px; padding: 13px; min-height: 0; }
    .hero-foto, .hero-foto-vazia {
        width: 58px;
        height: 58px;
        flex-basis: 58px;
        border-width: 3px;
    }
    .hero-foto-vazia { font-size: 22px; }
    .hero-info { flex: 1 1 calc(100% - 72px); }
    .hero-label { font-size: 9px; }
    .hero-nome { font-size: 16px; line-height: 1.25; }
    .hero-sub { font-size: 11px; line-height: 1.4; }
    .hero-votos {
        flex: 1 1 100%;
        margin-left: 0;
        padding-top: 8px;
        border-top: 1px solid rgba(255,255,255,0.28);
        text-align: left;
    }
    .hero-total { font-size: 26px; }
    .kpi { padding: 10px; border-radius: 12px; }
    .kpi-l, .kpi-d { font-size: 10px; }
    .kpi-v { font-size: 17px; letter-spacing: -0.2px; }
    .rk-box { padding: 10px; }
    .rk-row { grid-template-columns: 20px minmax(0, 1fr) 76px; gap: 6px; }
    .rk-nome { font-size: 11px; }
    .rk-val { font-size: 10px; }
    .rk-val b { font-size: 11px; }
    .sidebar-author { gap: 9px; padding: 10px 6px 13px; }
    .sidebar-author-icon { width: 38px; height: 38px; flex-basis: 38px; }
    .sidebar-author-name { font-size: 12px; }
    .sidebar-author-sub { font-size: 10px; }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        max-width: 100%;
        overflow-x: auto;
    }
    [data-testid="stPlotlyChart"] { max-width: 100%; }
}
/* Em telas estreitas, evita que gráficos causem estouro horizontal. */
[data-testid="stPlotlyChart"] > div { max-width: 100%; }


@media (max-width: 600px) {
    /* Os quatro KPIs ficam em uma grade 2x2, quando o Streamlit permite. */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .kpi) {
        flex-wrap: wrap !important;
        gap: 0.55rem !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .kpi) > div[data-testid="column"] {
        flex: 1 1 calc(50% - 0.55rem) !important;
        min-width: calc(50% - 0.55rem) !important;
    }
}


@media (max-width: 600px) {
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stPlotlyChart"]) {
        flex-wrap: wrap !important;
    }
}

</style>
""", unsafe_allow_html=True)


# ---------------- FUNÇÕES AUXILIARES ----------------

def normalizar_nome(nome):
    nome = str(nome).strip().upper()
    nome = unicodedata.normalize("NFKD", nome)
    return "".join(c for c in nome if not unicodedata.combining(c))


def fmt_numero(valor):
    return f"{int(valor):,}".replace(",", ".")


def fmt_pct(valor):
    return f"{valor:.2f}%".replace(".", ",")


def iniciais(nome):
    partes = [p for p in str(nome).split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def kpi(rotulo, valor, detalhe):
    return (
        f'<div class="kpi"><div class="kpi-l">{rotulo}</div>'
        f'<div class="kpi-v">{valor}</div><div class="kpi-d">{detalhe}</div></div>'
    )


def insight(titulo, texto):
    return f'<div class="insight"><b>{titulo}</b>{texto}</div>'


@st.cache_data
def carregar_opcoes():
    d = pl.scan_parquet(str(PARQUET))

    cargos = (
        d.select(["CD_CARGO", "DS_CARGO"])
        .unique()
        .sort("DS_CARGO")
        .collect()
        .to_pandas()
    )

    turnos = (
        d.select("NR_TURNO")
        .unique()
        .sort("NR_TURNO")
        .collect()["NR_TURNO"].to_list()
    )

    municipios = (
        d.select(["CD_MUNICIPIO", "NM_MUNICIPIO"])
        .unique()
        .sort("NM_MUNICIPIO")
        .collect()
        .to_pandas()
    )

    return cargos, turnos, municipios


@st.cache_data
def carregar_candidatos(cargo, turno):
    d = pl.scan_parquet(str(PARQUET)).filter(
        (pl.col("CD_CARGO") == str(cargo))
        & (pl.col("NR_TURNO") == str(turno))
        & pl.col("SQ_CANDIDATO").is_not_null()
        & (pl.col("SQ_CANDIDATO") != "")
    )

    return (
        d.group_by([
            "SQ_CANDIDATO", "NR_VOTAVEL", "NM_VOTAVEL"
        ])
        .agg(pl.col("QT_VOTOS").sum().alias("VOTOS"))
        .sort("VOTOS", descending=True)
        .collect()
        .to_pandas()
    )


@st.cache_data
def carregar_mapa():
    if not ARQUIVO_MAPA.exists():
        return None, None

    leitor = shapefile.Reader(
        str(ARQUIVO_MAPA), encoding="utf-8"
    )
    campos = [f[0] for f in leitor.fields[1:]]

    campo_nome = next(
        (c for c in campos
         if c.upper() in ("NM_MUN", "NM_MUNICIPIO", "NOME")),
        None
    )

    if campo_nome is None:
        raise ValueError(
            f"Campo de nome municipal não identificado: {campos}"
        )

    features = []
    nomes = []

    for item in leitor.iterShapeRecords():
        registro = dict(zip(campos, item.record))
        nome = str(registro[campo_nome]).strip()
        chave = normalizar_nome(nome)

        features.append({
            "type": "Feature",
            "id": chave,
            "properties": {"municipio": nome},
            "geometry": item.shape.__geo_interface__
        })
        nomes.append({"chave": chave, "municipio_mapa": nome})

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    return geojson, pd.DataFrame(nomes)


def caminho_foto(sq):
    if sq is None or pd.isna(sq):
        return None
    arquivo = FOTOS / f"FMT{str(sq).strip()}_div.jpg"
    return arquivo if arquivo.exists() else None


def foto_html(sq, nome):
    """Foto circular do candidato; sem foto, mostra as iniciais."""
    foto = caminho_foto(sq)
    if foto:
        try:
            b64 = base64.b64encode(foto.read_bytes()).decode("ascii")
            return (
                f'<img class="hero-foto" src="data:image/jpeg;base64,{b64}" '
                f'alt="Foto de {html.escape(str(nome))}">'
            )
        except Exception:
            pass
    return f'<div class="hero-foto-vazia">{html.escape(iniciais(nome))}</div>'


@st.cache_data(show_spinner=False)
def carregar_totais_gerais(cargo, turno, caminho_parquet):
    """Cacheia o total de votos por município para evitar reler o arquivo a cada interação."""
    return (
        pl.scan_parquet(caminho_parquet)
        .filter(
            (pl.col("CD_CARGO") == str(cargo))
            & (pl.col("NR_TURNO") == str(turno))
        )
        .group_by(["CD_MUNICIPIO", "NM_MUNICIPIO"])
        .agg(pl.col("QT_VOTOS").sum().alias("TOTAL_GERAL"))
        .collect()
        .to_pandas()
    )


@st.cache_data(show_spinner=False)
def carregar_totais_candidatos(cargo, turno, ids_candidatos, caminho_parquet):
    """Cacheia o total estadual dos candidatos selecionados."""
    return (
        pl.scan_parquet(caminho_parquet)
        .filter(
            (pl.col("CD_CARGO") == str(cargo))
            & (pl.col("NR_TURNO") == str(turno))
            & pl.col("SQ_CANDIDATO").is_in(list(ids_candidatos))
        )
        .group_by("SQ_CANDIDATO")
        .agg(pl.col("QT_VOTOS").sum().alias("TOTAL_CANDIDATO"))
        .collect()
        .to_pandas()
    )


# ---------------- EXPORTAÇÃO EM PDF (gerado no servidor, mapa vetorial) ----------------

def _pdf_txt(texto):
    """Garante que o texto só tenha caracteres suportados pelas fontes padrão do PDF."""
    return str(texto).encode("cp1252", "replace").decode("cp1252")


def _ajustar_fonte(texto, fonte, tamanho, largura_max, minimo=6.0):
    while tamanho > minimo and stringWidth(texto, fonte, tamanho) > largura_max:
        tamanho -= 0.5
    return tamanho


def _cor_escala(t):
    """Mesma escala de cores do mapa do painel (amarelo → vermelho escuro)."""
    paradas = [(0.0, "#f4f7fb"), (0.25, "#fed976"), (0.55, "#fd8d3c"),
               (0.8, "#e34a33"), (1.0, "#99000d")]
    t = max(0.0, min(1.0, float(t)))
    for (t0, c0), (t1, c1) in zip(paradas, paradas[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            a, b = colors.HexColor(c0), colors.HexColor(c1)
            return colors.Color(
                a.red + (b.red - a.red) * f,
                a.green + (b.green - a.green) * f,
                a.blue + (b.blue - a.blue) * f,
            )
    return colors.HexColor(paradas[-1][1])


def _gradiente(c, x, y, w, h, raio, cor0, cor1):
    c.saveState()
    caminho = c.beginPath()
    caminho.roundRect(x, y, w, h, raio)
    c.clipPath(caminho, stroke=0, fill=0)
    c.linearGradient(x, y, x + w, y, (colors.HexColor(cor0), colors.HexColor(cor1)))
    c.restoreState()


def _poligonos(geometria):
    if geometria["type"] == "Polygon":
        return [list(geometria["coordinates"])]
    if geometria["type"] == "MultiPolygon":
        return [list(p) for p in geometria["coordinates"]]
    return []


def _desenhar_mapa(c, geojson, valores, x, y, w, h, vmin, vmax):
    """Desenha o mapa coroplético em vetor direto no PDF (não precisa de kaleido/Chrome)."""
    feicoes = [(f["id"], _poligonos(f["geometry"])) for f in geojson["features"]]
    pontos = [p for _, polis in feicoes for poli in polis for anel in poli for p in anel]
    if not pontos:
        return
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    lon_min, lon_max, lat_min, lat_max = min(lons), max(lons), min(lats), max(lats)
    kx = math.cos(math.radians((lat_min + lat_max) / 2))
    span_x = (lon_max - lon_min) * kx or 1.0
    span_y = (lat_max - lat_min) or 1.0
    escala = min(w / span_x, h / span_y)
    off_x = x + (w - span_x * escala) / 2
    off_y = y + (h - span_y * escala) / 2
    faixa = (vmax - vmin) or 1.0

    c.setLineWidth(0.25)
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    for chave, polis in feicoes:
        valor = valores.get(chave, 0.0)
        c.setFillColor(_cor_escala((valor - vmin) / faixa))
        caminho = c.beginPath()
        for poli in polis:
            for anel in poli:
                passo = max(1, len(anel) // 800)  # simplifica anéis muito detalhados
                pts = list(anel)[::passo]
                if len(pts) < 3:
                    continue
                caminho.moveTo(off_x + (pts[0][0] - lon_min) * kx * escala,
                               off_y + (pts[0][1] - lat_min) * escala)
                for p in pts[1:]:
                    caminho.lineTo(off_x + (p[0] - lon_min) * kx * escala,
                                   off_y + (p[1] - lat_min) * escala)
                caminho.close()
        c.drawPath(caminho, stroke=1, fill=1, fillMode=FILL_EVEN_ODD)


def _texto_insight(card_html):
    m = re.match(r'<div class="insight"><b>(.*?)</b>(.*)</div>', card_html, re.S)
    titulo, corpo = (m.group(1), m.group(2)) if m else ("", card_html)
    limpar = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s))
    return limpar(titulo), limpar(corpo)


def gerar_pdf(ctx):
    """Monta o relatório em PDF (A4 paisagem, 2 páginas) a partir do contexto do painel."""
    buf = io.BytesIO()
    W, H = landscape(A4)
    M = 28
    util = W - 2 * M
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(_pdf_txt("Painel Eleitoral - Mato Grosso"))
    c.setAuthor("Alex Flavio Junior de Carvalho")

    TX = colors.HexColor("#0f172a")
    MUT = colors.HexColor("#64748b")
    BD = colors.HexColor("#e2e8f0")
    BG = colors.HexColor("#f1f5f9")
    VERDE = colors.HexColor("#16a34a")
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    total_pag = 2

    def Y(topo):
        return H - topo

    def rodape(n):
        c.setFont("Helvetica", 7)
        c.setFillColor(MUT)
        c.drawString(M, 16, _pdf_txt("Fonte: arquivo de resultados eleitorais do TSE processado localmente."))
        c.drawRightString(W - M, 16, _pdf_txt(f"Gerado em {agora} · Página {n}/{total_pag}"))

    def cabecalho(titulo, sub):
        c.setFillColor(TX)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(M, Y(40), _pdf_txt(titulo))
        c.setFillColor(MUT)
        c.setFont("Helvetica", 9.5)
        c.drawString(M, Y(55), _pdf_txt(sub))

    municipio_txt = ctx["municipio"] if ctx["municipio"] != "Todos" else "Todos os municípios"
    sub = f"{ctx['cargo']} · Turno {ctx['turno']} · {municipio_txt}"

    # ======================= PÁGINA 1 =======================
    cabecalho("Painel Eleitoral — Mato Grosso", sub)

    # ---- Cartões dos candidatos (com foto) ----
    herois = ctx["herois"]
    n = max(1, len(herois))
    gap = 10
    hw = (util - gap * (n - 1)) / n
    h_top, h_alt = 66, 70
    for i, her in enumerate(herois):
        x = M + i * (hw + gap)
        y = Y(h_top + h_alt)
        _gradiente(c, x, y, hw, h_alt, 12, "#4f46e5", "#06b6d4")

        r = 26
        cx, cy = x + 14 + r, y + h_alt / 2
        c.setFillColor(colors.white)
        c.circle(cx, cy, r + 2, stroke=0, fill=1)
        desenhou = False
        if her.get("foto"):
            try:
                img = ImageReader(str(her["foto"]))
                iw, ih = img.getSize()
                esc = max(2 * r / iw, 2 * r / ih)
                dw, dh = iw * esc, ih * esc
                c.saveState()
                caminho = c.beginPath()
                caminho.circle(cx, cy, r)
                c.clipPath(caminho, stroke=0, fill=0)
                c.drawImage(img, cx - dw / 2, cy + r - dh, dw, dh)
                c.restoreState()
                desenhou = True
            except Exception:
                desenhou = False
        if not desenhou:
            c.setFillColor(colors.HexColor("#6366f1"))
            c.circle(cx, cy, r, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(cx, cy - 6, _pdf_txt(iniciais(her["nome"])))

        tx = cx + r + 14
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 7)
        c.drawString(tx, y + h_alt - 18, _pdf_txt(f"CANDIDATO · Nº {her['numero']}"))
        nome = _pdf_txt(her["nome"])
        if n == 1:
            larg_nome = hw - (tx - x) - 120
        else:
            larg_nome = hw - (tx - x) - 10
        fs = _ajustar_fonte(nome, "Helvetica-Bold", 14, larg_nome, 7)
        c.setFont("Helvetica-Bold", fs)
        c.drawString(tx, y + h_alt - 34, nome)
        if n == 1:
            c.setFont("Helvetica", 7.5)
            c.drawString(tx, y + h_alt - 48, _pdf_txt(
                f"Votado em {her['municipios_com_votos']} de {her['total_municipios']} municípios · "
                f"Líder: {her['cidade_lider']} ({fmt_numero(her['votos_cidade_lider'])})"))
            c.setFont("Helvetica", 7)
            c.drawRightString(x + hw - 16, y + h_alt - 18, "TOTAL DE VOTOS")
            c.setFont("Helvetica-Bold", 24)
            c.drawRightString(x + hw - 16, y + h_alt - 44, fmt_numero(her["votos"]))
        else:
            c.setFont("Helvetica-Bold", 15)
            c.drawString(tx, y + h_alt - 52, f"{fmt_numero(her['votos'])} votos")
            c.setFont("Helvetica", 7)
            c.drawString(tx, y + h_alt - 63, _pdf_txt(
                f"{her['municipios_com_votos']} de {her['total_municipios']} municípios"))

    # ---- KPIs ----
    kpis = ctx["kpis"]
    if kpis:
        kg = 10
        kw = (util - kg * (len(kpis) - 1)) / len(kpis)
        k_top, k_alt = 146, 46
        for i, (rot, valor, det) in enumerate(kpis):
            x = M + i * (kw + kg)
            y = Y(k_top + k_alt)
            c.setFillColor(BG)
            c.setStrokeColor(BD)
            c.setLineWidth(0.6)
            c.roundRect(x, y, kw, k_alt, 8, stroke=1, fill=1)
            c.setFillColor(MUT)
            c.setFont("Helvetica", 7.5)
            c.drawString(x + 10, y + k_alt - 13, _pdf_txt(rot))
            valor = _pdf_txt(valor)
            fs = _ajustar_fonte(valor, "Helvetica-Bold", 13, kw - 20, 7)
            c.setFillColor(TX)
            c.setFont("Helvetica-Bold", fs)
            c.drawString(x + 10, y + k_alt - 28, valor)
            c.setFillColor(VERDE)
            c.setFont("Helvetica", 7.5)
            c.drawString(x + 10, y + k_alt - 40, _pdf_txt(det))

    # ---- Mapa + ranking ----
    sec_top, cont_top, cont_bot = 210, 218, 561
    cont_h = cont_bot - cont_top
    mapa_w = 340
    rank_x = M + mapa_w + 20
    rank_w = util - mapa_w - 20
    metrica_rot = ctx["metrica_rotulo"]

    c.setFillColor(TX)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(M, Y(sec_top), _pdf_txt(f"Mapa de votação · {metrica_rot}"))
    c.drawString(rank_x, Y(sec_top), _pdf_txt(
        f"Top {len(ctx['topo']) if ctx['topo'] is not None else 0} municípios · {ctx.get('nome_principal', '')}"))

    # caixa do mapa
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(BD)
    c.roundRect(M, Y(cont_bot), mapa_w, cont_h, 10, stroke=1, fill=1)
    mapa = ctx.get("mapa")
    if mapa:
        valores = mapa["valores"]
        vmin, vmax = 0.0, max(valores.values()) if valores else 1.0
        _desenhar_mapa(c, mapa["geojson"], valores,
                       M + 8, Y(cont_bot) + 40, mapa_w - 16, cont_h - 52, vmin, vmax)
        # legenda horizontal
        lx, lw, ly = M + 30, mapa_w - 60, Y(cont_bot) + 22
        passos = 40
        for k in range(passos):
            c.setFillColor(_cor_escala(k / (passos - 1)))
            c.rect(lx + lw * k / passos, ly, lw / passos + 0.5, 7, stroke=0, fill=1)
        fmt = fmt_numero if ctx["usar_votos"] else fmt_pct
        c.setFillColor(MUT)
        c.setFont("Helvetica", 7)
        c.drawString(lx, ly - 9, fmt(vmin))
        c.drawRightString(lx + lw, ly - 9, fmt(vmax))
        c.drawCentredString(lx + lw / 2, ly - 9, _pdf_txt(
            f"{metrica_rot} · {mapa['candidato']}"[:70]))
    else:
        c.setFillColor(MUT)
        c.setFont("Helvetica", 9)
        c.drawCentredString(M + mapa_w / 2, Y(cont_top + cont_h / 2), "Mapa indisponível")

    # caixa do ranking
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(BD)
    c.roundRect(rank_x, Y(cont_bot), rank_w, cont_h, 10, stroke=1, fill=1)
    topo = ctx["topo"]
    if topo is not None and len(topo) > 0:
        col = "VOTOS" if ctx["usar_votos"] else "% da votação geral"
        maximo = float(topo[col].max()) or 1.0
        rh = min(26.0, (cont_h - 16) / len(topo))
        barra_max = rank_w - 26 - 120
        for pos, (_, r) in enumerate(topo.iterrows(), start=1):
            rt = cont_top + 8 + (pos - 1) * rh
            c.setFillColor(MUT)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(rank_x + 14, Y(rt + 11), str(pos))
            c.setFillColor(TX)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(rank_x + 28, Y(rt + 9), _pdf_txt(str(r["NM_MUNICIPIO"])[:38]))
            # barra
            bw = max(3.0, float(r[col]) / maximo * barra_max)
            by = Y(rt + 18)
            c.setFillColor(BD)
            c.roundRect(rank_x + 28, by, barra_max, 4.5, 2, stroke=0, fill=1)
            _gradiente(c, rank_x + 28, by, bw, 4.5, 2, "#6366f1", "#06b6d4")
            # valores
            if ctx["usar_votos"]:
                v1, v2 = fmt_numero(r["VOTOS"]), f"{fmt_pct(r['% da votação geral'])} geral"
            else:
                v1, v2 = fmt_pct(r["% da votação geral"]), f"{fmt_numero(r['VOTOS'])} votos"
            c.setFillColor(TX)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(rank_x + rank_w - 12, Y(rt + 9), v1)
            c.setFillColor(MUT)
            c.setFont("Helvetica", 7)
            c.drawRightString(rank_x + rank_w - 12, Y(rt + 18), v2)

    rodape(1)
    c.showPage()

    # ======================= PÁGINA 2 =======================
    cabecalho("Análises e detalhamento", sub)

    # ---- Insights ----
    cards = [_texto_insight(h) for h in ctx.get("insights", [])]
    if cards:
        ig = 12
        iw = (util - ig * (len(cards) - 1)) / len(cards)
        i_top, i_alt = 66, 96
        for i, (titulo, corpo) in enumerate(cards):
            x = M + i * (iw + ig)
            y = Y(i_top + i_alt)
            c.setFillColor(BG)
            c.setStrokeColor(BD)
            c.setLineWidth(0.6)
            c.roundRect(x, y, iw, i_alt, 8, stroke=1, fill=1)
            c.setFillColor(colors.HexColor("#6366f1"))
            c.rect(x, y + 6, 3, i_alt - 12, stroke=0, fill=1)
            c.setFillColor(TX)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(x + 14, y + i_alt - 17, _pdf_txt(titulo))
            c.setFont("Helvetica", 8.5)
            linhas = simpleSplit(_pdf_txt(corpo), "Helvetica", 8.5, iw - 28)[:6]
            for j, linha in enumerate(linhas):
                c.drawString(x + 14, y + i_alt - 32 - j * 11, linha)

    # ---- Tabela de municípios do candidato principal ----
    rp = ctx.get("rp")
    perfis = ctx.get("perfis", {})
    if rp is not None and len(rp) > 0:
        t_top = 190
        c.setFillColor(TX)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(M, Y(t_top), _pdf_txt(f"Municípios do candidato principal · {ctx.get('nome_principal', '')}"))

        cab_top, rh = t_top + 8, 13.6
        max_lin = int((cont_bot - cab_top - 16) / rh)
        linhas_df = rp.sort_values("VOTOS", ascending=False).head(max_lin)
        c.setFillColor(MUT)
        c.setFont("Helvetica", 7.5)
        c.drawRightString(W - M, Y(t_top),
                          _pdf_txt(f"Exibindo {len(linhas_df)} de {len(rp)} municípios (ordem por votos)"))

        pesos = [24, 220, 110, 100, 150, 150]
        esc = util / sum(pesos)
        larg = [p * esc for p in pesos]
        xs = [M]
        for l in larg[:-1]:
            xs.append(xs[-1] + l)
        titulos = ["#", "Município", "Perfil", "Votos", "% do total do candidato", "% da votação geral"]

        c.setFillColor(BG)
        c.rect(M, Y(cab_top + 16), util, 16, stroke=0, fill=1)
        c.setFillColor(MUT)
        c.setFont("Helvetica-Bold", 7.5)
        for k, tit in enumerate(titulos):
            if k >= 3:
                c.drawRightString(xs[k] + larg[k] - 8, Y(cab_top + 11), tit)
            else:
                c.drawString(xs[k] + 6, Y(cab_top + 11), tit)

        for i, (_, r) in enumerate(linhas_df.iterrows()):
            rt = cab_top + 16 + i * rh
            if i % 2 == 1:
                c.setFillColor(colors.HexColor("#f8fafc"))
                c.rect(M, Y(rt + rh), util, rh, stroke=0, fill=1)
            c.setFillColor(TX)
            c.setFont("Helvetica", 8)
            base = Y(rt + 9.5)
            c.drawString(xs[0] + 6, base, str(i + 1))
            c.drawString(xs[1] + 6, base, _pdf_txt(str(r["NM_MUNICIPIO"])[:42]))
            c.drawString(xs[2] + 6, base, _pdf_txt(perfis.get(r["NM_MUNICIPIO"], "—")))
            c.drawRightString(xs[3] + larg[3] - 8, base, fmt_numero(r["VOTOS"]))
            c.drawRightString(xs[4] + larg[4] - 8, base, fmt_pct(r["% do total do candidato"]))
            c.drawRightString(xs[5] + larg[5] - 8, base, fmt_pct(r["% da votação geral"]))

    rodape(2)
    c.showPage()
    c.save()
    return buf.getvalue()


if not PARQUET.exists():
    st.error("Parquet não encontrado. Execute app\\processar.py.")
    st.stop()

try:
    cargos, turnos, municipios = carregar_opcoes()
except Exception as erro:
    st.error(f"Erro ao carregar os dados: {erro}")
    st.stop()

# ---------------- SIDEBAR ----------------

st.sidebar.markdown("""
<div class="sidebar-author">
  <div class="sidebar-author-icon" aria-hidden="true">
    <svg width="21" height="21" viewBox="0 0 24 24" fill="none"
         xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="8" r="3.4" stroke="currentColor" stroke-width="1.8"/>
      <path d="M5.5 20c.45-3.55 2.85-5.5 6.5-5.5s6.05 1.95 6.5 5.5"
            stroke="currentColor" stroke-width="1.8"
            stroke-linecap="round"/>
    </svg>
  </div>
  <div class="sidebar-author-copy">
    <div class="sidebar-author-label">DESENVOLVIDO POR</div>
    <div class="sidebar-author-name">Alex Flavio Junior de Carvalho</div>
    <div class="sidebar-author-sub">Análise de dados eleitorais · Mato Grosso</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.title("🗳️ Painel Eleitoral")
st.sidebar.caption("Mato Grosso · Resultados do TSE")
st.sidebar.divider()

cargo_label = st.sidebar.selectbox(
    "Cargo",
    cargos["DS_CARGO"].tolist()
)
cargo_id = cargos.loc[
    cargos["DS_CARGO"] == cargo_label, "CD_CARGO"
].iloc[0]

turno = st.sidebar.selectbox("Turno", turnos)

municipios_lista = ["Todos"] + municipios["NM_MUNICIPIO"].tolist()
municipio = st.sidebar.selectbox("Município", municipios_lista)

candidatos = carregar_candidatos(cargo_id, turno)

if candidatos.empty:
    st.warning("Não foram encontrados candidatos para esses filtros.")
    st.stop()

candidatos["ROTULO"] = candidatos.apply(
    lambda r: f"{r['NM_VOTAVEL']} — {r['NR_VOTAVEL']}",
    axis=1
)

rotulos = candidatos["ROTULO"].tolist()

principal = st.sidebar.selectbox(
    "Candidato principal",
    rotulos,
    index=0
)

comparar = st.sidebar.checkbox(
    "Comparar candidatos",
    value=False
)

selecionados = [principal]

if comparar:
    restantes = [r for r in rotulos if r != principal]
    adicionais = st.sidebar.multiselect(
        "Candidatos para comparação (até 2)",
        restantes,
        default=[],
        max_selections=2
    )
    selecionados += adicionais

metrica_escolha = st.sidebar.radio(
    "Métrica do mapa e do ranking",
    ["Votos", "% geral"],
    horizontal=True
)
usar_votos = metrica_escolha == "Votos"
col_metrica = "VOTOS" if usar_votos else "% da votação geral"
rotulo_metrica = "Votos" if usar_votos else "% da votação geral"

st.sidebar.divider()
st.sidebar.caption("Os filtros são aplicados aos indicadores, mapa, ranking e insights.")

# ---------------- CONSULTA DOS VOTOS ----------------

ids = candidatos.set_index("ROTULO")["SQ_CANDIDATO"].to_dict()
info = candidatos.set_index("ROTULO")

ids_selecionados = [str(ids[r]) for r in selecionados]

filtro = (
    (pl.col("CD_CARGO") == str(cargo_id))
    & (pl.col("NR_TURNO") == str(turno))
    & pl.col("SQ_CANDIDATO").is_in(ids_selecionados)
)

if municipio != "Todos":
    codigo_municipio = str(
        municipios.loc[
            municipios["NM_MUNICIPIO"] == municipio,
            "CD_MUNICIPIO"
        ].iloc[0]
    )
    filtro = filtro & (
        pl.col("CD_MUNICIPIO") == codigo_municipio
    )

colunas_voto = [
    "SQ_CANDIDATO", "NR_VOTAVEL", "NM_VOTAVEL",
    "CD_MUNICIPIO", "NM_MUNICIPIO", "QT_VOTOS"
]

with st.spinner("Carregando os dados do candidato e atualizando os indicadores..."):
    dados = (
        pl.scan_parquet(str(PARQUET))
        .filter(filtro)
        .select(colunas_voto)
        .group_by([
            "SQ_CANDIDATO", "NR_VOTAVEL", "NM_VOTAVEL",
            "CD_MUNICIPIO", "NM_MUNICIPIO"
        ])
        .agg(pl.col("QT_VOTOS").sum().alias("VOTOS"))
        .collect()
        .to_pandas()
    )

    if dados.empty:
        st.warning("Não há votos para a seleção atual.")
        st.stop()

    dados["CHAVE_MUNICIPIO"] = dados["NM_MUNICIPIO"].map(normalizar_nome)

    # Total geral de votos do cargo/turno, incluindo todos os candidatos.
    totais_gerais = carregar_totais_gerais(
        str(cargo_id), str(turno), str(PARQUET)
    )
    totais_gerais["CD_MUNICIPIO"] = totais_gerais["CD_MUNICIPIO"].astype(str)

    # ---------------- RANKING (calculado antes do layout) ----------------

    ranking = dados.copy()
    ranking["SQ_CANDIDATO"] = ranking["SQ_CANDIDATO"].astype(str)
    ranking["CD_MUNICIPIO"] = ranking["CD_MUNICIPIO"].astype(str)

    # Totais estaduais de cada candidato no cargo/turno selecionado.
    totais_candidatos = carregar_totais_candidatos(
        str(cargo_id), str(turno), tuple(ids_selecionados), str(PARQUET)
    )
    totais_candidatos["SQ_CANDIDATO"] = totais_candidatos["SQ_CANDIDATO"].astype(str)

    ranking = ranking.merge(totais_candidatos, on="SQ_CANDIDATO", how="left")
    ranking = ranking.merge(
        totais_gerais[["CD_MUNICIPIO", "TOTAL_GERAL"]],
        on="CD_MUNICIPIO",
        how="left"
    )
    ranking["VOTOS_NO_COMPARATIVO"] = ranking.groupby("NM_MUNICIPIO")["VOTOS"].transform("sum")
    ranking["% do total do candidato"] = (
        ranking["VOTOS"] / ranking["TOTAL_CANDIDATO"].replace(0, pd.NA) * 100
    ).fillna(0).astype(float)
    ranking["% da votação geral"] = (
        ranking["VOTOS"] / ranking["TOTAL_GERAL"].replace(0, pd.NA) * 100
    ).fillna(0).astype(float)
    ranking["% do comparativo"] = (
        ranking["VOTOS"] / ranking["VOTOS_NO_COMPARATIVO"].replace(0, pd.NA) * 100
    ).fillna(0).astype(float)

    ranking["Candidato"] = ranking.apply(
        lambda r: f"{r['NM_VOTAVEL']} ({r['NR_VOTAVEL']})",
        axis=1
    )

    # Dados do candidato principal (usado em KPIs, ranking lateral e insights).
    sq_principal = ids_selecionados[0]
    rp = ranking[ranking["SQ_CANDIDATO"] == sq_principal].sort_values(
        "VOTOS", ascending=False
    )

# ---------------- CABEÇALHO ----------------

col_titulo, col_pdf = st.columns([3, 1])
with col_titulo:
    st.title("Painel Eleitoral — Mato Grosso")
    st.caption("Elaborado por Alex Flavio Junior de Carvalho")
espaco_pdf = col_pdf.container()  # preenchido no fim do script, quando tudo já foi calculado

chips = [cargo_label, f"Turno {turno}",
         municipio if municipio != "Todos" else "Todos os municípios"]
st.markdown(
    "".join(f'<span class="chip">{html.escape(str(c))}</span>' for c in chips),
    unsafe_allow_html=True
)
st.write("")

# ---------------- CARTÕES DOS CANDIDATOS (com foto) ----------------

herois = []  # dados dos cartões, reaproveitados no PDF
colunas_cartao = st.columns(len(selecionados))

for coluna, rotulo in zip(colunas_cartao, selecionados):
    candidato = info.loc[rotulo]
    sq = str(candidato["SQ_CANDIDATO"])

    dados_candidato = dados[dados["SQ_CANDIDATO"].astype(str) == sq].copy()
    votos = int(dados_candidato["VOTOS"].sum())

    municipios_com_votos = int(
        dados_candidato.loc[dados_candidato["VOTOS"] > 0, "NM_MUNICIPIO"].nunique()
    )

    if not dados_candidato.empty:
        por_municipio = (
            dados_candidato.groupby("NM_MUNICIPIO", as_index=False)["VOTOS"]
            .sum()
            .sort_values("VOTOS", ascending=False)
        )
        cidade_lider = str(por_municipio.iloc[0]["NM_MUNICIPIO"])
        votos_cidade_lider = int(por_municipio.iloc[0]["VOTOS"])
    else:
        cidade_lider = "Sem votação"
        votos_cidade_lider = 0

    nome_bruto = str(candidato["NM_VOTAVEL"])
    herois.append({
        "nome": nome_bruto,
        "numero": str(candidato["NR_VOTAVEL"]),
        "votos": votos,
        "municipios_com_votos": municipios_com_votos,
        "total_municipios": TOTAL_MUNICIPIOS_MT,
        "cidade_lider": cidade_lider,
        "votos_cidade_lider": votos_cidade_lider,
        "foto": caminho_foto(sq),
    })
    nome = html.escape(nome_bruto)
    numero = html.escape(str(candidato["NR_VOTAVEL"]))

    with coluna:
        st.markdown(
            "".join([
                '<div class="hero">',
                foto_html(sq, nome_bruto),
                '<div class="hero-info">',
                f'<div class="hero-label">Candidato · Nº {numero}</div>',
                f'<div class="hero-nome">{nome}</div>',
                f'<div class="hero-sub">Votado em {municipios_com_votos} de '
                f'{TOTAL_MUNICIPIOS_MT} municípios · Líder: '
                f'{html.escape(cidade_lider)} ({fmt_numero(votos_cidade_lider)})</div>',
                '</div>',
                '<div class="hero-votos">',
                '<div class="hero-label">Total de votos</div>',
                f'<div class="hero-total">{fmt_numero(votos)}</div>',
                '</div></div>',
            ]),
            unsafe_allow_html=True
        )

# ---------------- KPIs DO CANDIDATO PRINCIPAL ----------------

kpis_pdf = []
if not rp.empty:
    st.write("")
    lider = rp.iloc[0]
    top3 = rp.head(3)["% do total do candidato"].sum()
    top10 = rp.head(10)["% do total do candidato"].sum()

    elegiveis = rp[rp["TOTAL_GERAL"].fillna(0) > 0]
    base_forca = elegiveis[elegiveis["VOTOS"] >= 100]
    if base_forca.empty:
        base_forca = elegiveis
    forca = (
        base_forca.sort_values("% da votação geral", ascending=False).iloc[0]
        if not base_forca.empty else None
    )

    kpis_pdf.append(("Município líder", str(lider["NM_MUNICIPIO"]),
                     f"{fmt_numero(lider['VOTOS'])} votos"))
    kpis_pdf.append(("Concentração Top 3", fmt_pct(top3), "do total do candidato"))
    if forca is not None:
        kpis_pdf.append(("Maior força relativa", str(forca["NM_MUNICIPIO"]),
                         f"{fmt_pct(forca['% da votação geral'])} da votação local"))
    kpis_pdf.append(("Concentração Top 10", fmt_pct(top10),
                     f"{fmt_pct(max(0, 100 - top10))} pulverizado"))

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(
        kpi("Município líder", html.escape(str(lider["NM_MUNICIPIO"])),
            f"{fmt_numero(lider['VOTOS'])} votos"),
        unsafe_allow_html=True
    )
    k2.markdown(
        kpi("Concentração Top 3", fmt_pct(top3), "do total do candidato"),
        unsafe_allow_html=True
    )
    if forca is not None:
        k3.markdown(
            kpi("Maior força relativa", html.escape(str(forca["NM_MUNICIPIO"])),
                f"{fmt_pct(forca['% da votação geral'])} da votação local"),
            unsafe_allow_html=True
        )
    k4.markdown(
        kpi("Concentração Top 10", fmt_pct(top10),
            f"{fmt_pct(max(0, 100 - top10))} pulverizado"),
        unsafe_allow_html=True
    )

st.divider()

# ---------------- MAPA DE CALOR + RANKING LADO A LADO ----------------

st.subheader("Mapa de votação e ranking de municípios")

dados_mapa_pdf = None
topo_pdf = None
col_mapa, col_rank = st.columns([1.35, 1], gap="large")

with col_mapa:
    try:
        geojson, nomes_mapa = carregar_mapa()

        if geojson is None:
            st.warning("A malha municipal do IBGE não foi encontrada.")
        else:
            if len(selecionados) > 1:
                # Chave dinâmica evita que o Streamlit reutilize o estado
                # do selectbox quando os candidatos selecionados mudam.
                chave_mapa = "candidato_mapa_" + "_".join(
                    re.sub(r"[^A-Za-z0-9_]", "", str(ids[r]))
                    for r in selecionados
                )
                escolhido_mapa = st.selectbox(
                    "Candidato exibido no mapa",
                    selecionados,
                    key=chave_mapa
                )
            else:
                escolhido_mapa = selecionados[0]

            sq_mapa = str(ids[escolhido_mapa])

            base_mapa = (
                ranking[ranking["SQ_CANDIDATO"] == sq_mapa]
                .groupby("CHAVE_MUNICIPIO", as_index=False)
                .agg(VOTOS=("VOTOS", "sum"),
                     PCT_GERAL=("% da votação geral", "sum"))
            )

            # Primeiro tenta o nome normalizado; se houver diferenças de grafia
            # entre a base eleitoral e o shapefile, tenta uma correspondência próxima.
            chaves_base = base_mapa["CHAVE_MUNICIPIO"].dropna().astype(str).tolist()
            mapa_chaves = set(nomes_mapa["chave"].astype(str))
            aliases = {}
            for chave_base in chaves_base:
                if chave_base not in mapa_chaves:
                    similares = get_close_matches(chave_base, list(mapa_chaves), n=1, cutoff=0.86)
                    if similares:
                        aliases[chave_base] = similares[0]

            base_mapa["CHAVE_MAPA"] = base_mapa["CHAVE_MUNICIPIO"].map(
                lambda chave: chave if chave in mapa_chaves else aliases.get(chave)
            )
            base_mapa_ok = base_mapa.dropna(subset=["CHAVE_MAPA"]).groupby(
                "CHAVE_MAPA", as_index=False
            ).agg(VOTOS=("VOTOS", "sum"), PCT_GERAL=("PCT_GERAL", "sum"))

            votos_mapa = nomes_mapa.merge(
                base_mapa_ok,
                left_on="chave",
                right_on="CHAVE_MAPA",
                how="left"
            )
            votos_mapa["VOTOS"] = votos_mapa["VOTOS"].fillna(0)
            votos_mapa["PCT_GERAL"] = votos_mapa["PCT_GERAL"].fillna(0)
            votos_mapa["VALOR"] = (
                votos_mapa["VOTOS"] if usar_votos else votos_mapa["PCT_GERAL"]
            )

            dados_mapa_pdf = {
                "geojson": geojson,
                "valores": dict(zip(votos_mapa["chave"], votos_mapa["VALOR"].astype(float))),
                "candidato": str(escolhido_mapa),
            }

            hover = {"VALOR": True if usar_votos else ":.2f", "chave": False}

            fig = px.choropleth_map(
                votos_mapa,
                geojson=geojson,
                locations="chave",
                featureidkey="id",
                color="VALOR",
                hover_name="municipio_mapa",
                hover_data=hover,
                color_continuous_scale=[
                    [0, "#f4f7fb"],
                    [0.25, "#fed976"],
                    [0.55, "#fd8d3c"],
                    [0.8, "#e34a33"],
                    [1, "#99000d"]
                ],
                map_style="carto-darkmatter",
                center={"lat": -12.6, "lon": -55.9},
                zoom=4.2,
                opacity=0.78,
                labels={"VALOR": rotulo_metrica}
            )

            fig.update_traces(
                marker_line_width=0.9,
                marker_line_color="rgba(226,232,240,0.9)"
            )
            fig.update_layout(
                height=680,
                margin={"r": 0, "t": 5, "l": 0, "b": 0},
                coloraxis_colorbar=dict(
                    title=rotulo_metrica,
                    orientation="h",
                    thickness=10,
                    len=0.6,
                    y=0.02,
                    x=0.5
                ),
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)

            encontrados = int((base_mapa["VOTOS"] > 0).sum())
            st.caption(
                f"{encontrados} municípios com votos para o candidato selecionado, "
                f"de {TOTAL_MUNICIPIOS_MT} municípios de Mato Grosso."
            )
            sem_correspondencia = [
                chave for chave in chaves_base
                if chave not in mapa_chaves and chave not in aliases
            ]
            if sem_correspondencia:
                st.warning(
                    "Alguns nomes da base eleitoral não coincidiram com o mapa: "
                    + ", ".join(sem_correspondencia)
                )

    except Exception as erro:
        st.error(f"Não foi possível montar o mapa: {erro}")

with col_rank:
    nome_rank = (
        html.escape(str(rp.iloc[0]["NM_VOTAVEL"])) if not rp.empty else ""
    )
    st.markdown(f"**Top {TOP_RANKING} municípios** · {nome_rank}")

    if rp.empty:
        st.info("O candidato principal não tem votos na seleção atual.")
    else:
        topo = rp.sort_values(col_metrica, ascending=False).head(TOP_RANKING)
        topo_pdf = topo.copy()
        maximo = float(topo[col_metrica].max()) or 1.0

        linhas = []
        for pos, (_, r) in enumerate(topo.iterrows(), start=1):
            largura = max(2.0, float(r[col_metrica]) / maximo * 100)
            if usar_votos:
                principal_txt = fmt_numero(r["VOTOS"])
                secundario_txt = f"{fmt_pct(r['% da votação geral'])} geral"
            else:
                principal_txt = fmt_pct(r["% da votação geral"])
                secundario_txt = f"{fmt_numero(r['VOTOS'])} votos"
            linhas.append(
                '<div class="rk-row">'
                f'<div class="rk-pos">{pos}</div>'
                '<div>'
                f'<div class="rk-nome">{html.escape(str(r["NM_MUNICIPIO"]))}</div>'
                f'<div class="rk-bar"><i style="width:{largura:.1f}%"></i></div>'
                '</div>'
                f'<div class="rk-val"><b>{principal_txt}</b><span>{secundario_txt}</span></div>'
                '</div>'
            )

        st.markdown(
            '<div class="rk-box">' + "".join(linhas) + '</div>',
            unsafe_allow_html=True
        )
        st.caption(
            "Ranking do candidato principal. A métrica (votos ou % da votação geral) "
            "é escolhida na barra lateral."
        )

st.divider()

# ---------------- DETALHAMENTO POR MUNICÍPIO ----------------

st.subheader("Detalhamento por município")
st.caption(
    "As porcentagens mostram: participação do município no total estadual do candidato; "
    "peso do candidato na votação geral do município para o cargo/turno; "
    "e participação dentro do grupo de candidatos comparados."
)

# Monta uma coluna para cada candidato e inclui votos + três percentuais.
tabela_votos = ranking.pivot_table(
    index="NM_MUNICIPIO",
    columns="Candidato",
    values="VOTOS",
    aggfunc="sum",
    fill_value=0
)
tabela_pct_candidato = ranking.pivot_table(
    index="NM_MUNICIPIO",
    columns="Candidato",
    values="% do total do candidato",
    aggfunc="sum",
    fill_value=0
).add_suffix(" · % do total do candidato")
tabela_pct_geral = ranking.pivot_table(
    index="NM_MUNICIPIO",
    columns="Candidato",
    values="% da votação geral",
    aggfunc="sum",
    fill_value=0
).add_suffix(" · % da votação geral")
tabela_pct_comparativo = ranking.pivot_table(
    index="NM_MUNICIPIO",
    columns="Candidato",
    values="% do comparativo",
    aggfunc="sum",
    fill_value=0
).add_suffix(" · % do comparativo")

tabela = pd.concat(
    [tabela_votos, tabela_pct_candidato, tabela_pct_geral, tabela_pct_comparativo],
    axis=1
).reset_index()

# Ordena pelo total de votos dos candidatos comparados no município.
tabela["Total comparado"] = tabela_votos.sum(axis=1).reindex(tabela["NM_MUNICIPIO"]).to_numpy()
tabela = tabela.sort_values("Total comparado", ascending=False)

# Formata percentuais para leitura e mantém votos como números inteiros.
for coluna in tabela.columns:
    if "· %" in str(coluna):
        tabela[coluna] = tabela[coluna].map(fmt_pct)
for coluna in tabela.columns:
    if coluna != "NM_MUNICIPIO" and "· %" not in str(coluna):
        tabela[coluna] = tabela[coluna].map(
            lambda x: fmt_numero(x) if pd.notna(x) and str(x).replace(".", "", 1).isdigit() else x
        )

# Perfil do município para o candidato principal.
perfis = {}
if not rp.empty:
    limite_volume = rp["VOTOS"].quantile(0.9)

    def classificar(linha):
        if linha["% da votação geral"] >= 20:
            return "Bastião"
        if linha["VOTOS"] >= limite_volume:
            return "Alto volume"
        return "Em observação"

    perfis = rp.set_index("NM_MUNICIPIO").apply(classificar, axis=1).to_dict()
    tabela.insert(1, "Perfil (principal)",
                  tabela["NM_MUNICIPIO"].map(perfis).fillna("—"))

busca = st.text_input("Buscar município", placeholder="Digite o nome do município…")
tabela_vis = tabela
if busca.strip():
    alvo = normalizar_nome(busca)
    tabela_vis = tabela[
        tabela["NM_MUNICIPIO"].map(normalizar_nome).str.contains(alvo, regex=False)
    ]

st.dataframe(tabela_vis, use_container_width=True, hide_index=True)

st.download_button(
    "⬇ Exportar ranking em CSV",
    tabela.to_csv(index=False).encode("utf-8-sig"),
    file_name="ranking_municipal_mt.csv",
    mime="text/csv"
)

# ---------------- GRÁFICO COMPARATIVO ----------------

if comparar and len(selecionados) > 1:
    st.subheader("Comparativo entre candidatos")
    st.caption(
        "Gráfico em linha dos votos por município. Os municípios são ordenados "
        "pelo total de votos dos candidatos selecionados."
    )
    grafico = ranking.pivot_table(
        index="NM_MUNICIPIO",
        columns="Candidato",
        values="VOTOS",
        aggfunc="sum",
        fill_value=0
    )
    ordem_municipios = tabela_votos.sum(axis=1).sort_values(ascending=False).index.tolist()
    grafico = grafico.reindex(ordem_municipios).fillna(0).reset_index()
    grafico_longo = grafico.melt(
        id_vars="NM_MUNICIPIO",
        var_name="Candidato",
        value_name="Votos"
    )
    fig_linha = px.line(
        grafico_longo,
        x="NM_MUNICIPIO",
        y="Votos",
        color="Candidato",
        markers=True,
        labels={
            "NM_MUNICIPIO": "Município",
            "Votos": "Votos",
            "Candidato": "Candidato"
        },
        title="Votação por município"
    )
    fig_linha.update_layout(
        height=520,
        xaxis_tickangle=-55,
        margin={"r": 20, "t": 55, "l": 10, "b": 110},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig_linha, use_container_width=True)

# ---------------- INSIGHTS AUTOMÁTICOS ----------------

st.subheader("3 insights para análise")
cartoes = []

if not ranking.empty:
    total_selecionados = ranking.groupby("SQ_CANDIDATO")["VOTOS"].sum().sort_values(ascending=False)
    nomes_por_id = (
        ranking.drop_duplicates("SQ_CANDIDATO")
        .set_index("SQ_CANDIDATO")["NM_VOTAVEL"]
        .to_dict()
    )
    lider_id = str(total_selecionados.index[0])
    lider_nome = html.escape(str(nomes_por_id.get(lider_id, "Candidato líder")))

    # Insight 1: município de maior votação do candidato líder.
    votos_lider = ranking[ranking["SQ_CANDIDATO"] == lider_id].sort_values("VOTOS", ascending=False)
    if not votos_lider.empty:
        linha_top = votos_lider.iloc[0]
        cartoes.append(insight(
            "1. Principal reduto",
            f"{lider_nome} teve seu maior volume em "
            f"{html.escape(str(linha_top['NM_MUNICIPIO']))}, com "
            f"{fmt_numero(linha_top['VOTOS'])} votos "
            f"({fmt_pct(linha_top['% do total do candidato'])} do total estadual desse candidato)."
        ))

    # Insight 2: município onde o candidato principal tem maior força relativa.
    if not rp.empty and forca is not None:
        cartoes.append(insight(
            "2. Força relativa",
            f"{html.escape(str(forca['NM_MUNICIPIO']))} é onde o candidato principal pesa mais "
            f"na votação local: {fmt_pct(forca['% da votação geral'])} "
            f"({fmt_numero(forca['VOTOS'])} votos). Considera municípios com ao menos 100 votos."
        ))

    # Insight 3: vantagem local (comparação) ou oportunidade (candidato único).
    matriz = ranking.pivot_table(
        index="NM_MUNICIPIO",
        columns="Candidato",
        values="VOTOS",
        aggfunc="sum",
        fill_value=0
    )
    if matriz.shape[1] >= 2:
        diferencas = matriz.apply(
            lambda linha: linha.sort_values(ascending=False).iloc[0] - linha.sort_values(ascending=False).iloc[1],
            axis=1
        ).sort_values(ascending=False)
        cartoes.append(insight(
            "3. Maior vantagem local",
            f"Em {html.escape(str(diferencas.index[0]))}, a diferença entre o candidato "
            f"mais votado e o segundo colocado entre os selecionados foi de "
            f"{fmt_numero(diferencas.iloc[0])} votos."
        ))
    elif not rp.empty:
        grandes = rp.head(10)
        grandes = grandes[grandes["TOTAL_GERAL"].fillna(0) > 0]
        if len(grandes) >= 2:
            opp = grandes.sort_values("% da votação geral").iloc[0]
            cartoes.append(insight(
                "3. Espaço de crescimento",
                f"{html.escape(str(opp['NM_MUNICIPIO']))} está entre os maiores redutos "
                f"({fmt_numero(opp['VOTOS'])} votos), mas representa só "
                f"{fmt_pct(opp['% da votação geral'])} da votação local: "
                f"o maior potencial de expansão entre os 10 maiores municípios."
            ))

if cartoes:
    for coluna, cartao in zip(st.columns(len(cartoes)), cartoes):
        coluna.markdown(cartao, unsafe_allow_html=True)

st.caption("Fonte: arquivo de resultados eleitorais do TSE processado localmente.")

# ---------------- EXPORTAÇÃO EM PDF ----------------
# O botão fica no cabeçalho (espaco_pdf), mas só é montado aqui, depois que
# todos os dados da tela foram calculados.

with espaco_pdf:
    if not REPORTLAB_OK:
        st.caption("Para exportar em PDF, instale: pip install reportlab")
    else:
        assinatura_pdf = (
            str(cargo_id), str(turno), municipio, tuple(ids_selecionados),
            metrica_escolha,
            dados_mapa_pdf["candidato"] if dados_mapa_pdf else ""
        )

        if st.button("📄 Gerar PDF", use_container_width=True):
            with st.spinner("Montando o PDF…"):
                try:
                    st.session_state["pdf_bytes"] = gerar_pdf({
                        "cargo": cargo_label,
                        "turno": turno,
                        "municipio": municipio,
                        "herois": herois,
                        "kpis": kpis_pdf,
                        "metrica_rotulo": rotulo_metrica,
                        "usar_votos": usar_votos,
                        "nome_principal": str(rp.iloc[0]["NM_VOTAVEL"]) if not rp.empty else "",
                        "mapa": dados_mapa_pdf,
                        "topo": topo_pdf,
                        "rp": rp,
                        "perfis": perfis,
                        "insights": cartoes,
                    })
                    st.session_state["pdf_assinatura"] = assinatura_pdf
                except Exception as erro:
                    st.session_state.pop("pdf_bytes", None)
                    st.error(f"Não foi possível gerar o PDF: {erro}")

        if (
            "pdf_bytes" in st.session_state
            and st.session_state.get("pdf_assinatura") == assinatura_pdf
        ):
            nome_arquivo = re.sub(
                r"[^a-z0-9]+", "_",
                normalizar_nome(herois[0]["nome"] if herois else "painel").lower()
            ).strip("_")
            st.download_button(
                "⬇ Baixar PDF",
                st.session_state["pdf_bytes"],
                file_name=f"painel_eleitoral_{nome_arquivo}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
