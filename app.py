import json
import streamlit as st
from streamlit_lottie import st_lottie

st.set_page_config(
    page_title="QA Netting Bunga RAK",
    page_icon="🚀",
    layout="wide",
)

ASSET_POSTGRES = "assets/postgres.png"
ASSET_JSON = "assets/json.png"
ASSET_LOTTIE_HERO = "assets/lottie_hello.json"


@st.cache_data
def load_lottie_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


lottie_hero = load_lottie_file(ASSET_LOTTIE_HERO)

# ========== CUSTOM CSS (gaya sama kayak DevMate Suite) ==========
st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    .main { padding: 0 !important; }
    .block-container { max-width: 100% !important; padding: 0 !important; }

    .hero {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
        padding: 2rem;
        border-bottom: 1px solid #30363d;
    }
    .hero-inner { max-width: 1100px; margin: 0 auto; }
    .hero h1 { font-size: 2.5rem; font-weight: 800; color: #fff; margin: 0; }
    .hero p { color: #8b949e; font-size: 1.1rem; margin-top: 0.5rem; }

    .cards-container {
        display: flex;
        flex-wrap: wrap;
        gap: 1.2rem;
        padding: 1.5rem 2rem;
        max-width: 1400px;
        margin: 0 auto;
    }

    .card-wrapper {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 14px;
        padding: 1.3rem;
        transition: all 0.25s ease;
    }
    .card-wrapper:hover {
        border-color: #ff6b35;
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(255, 107, 53, 0.12);
    }

    .card-icon-emoji {
        font-size: 60px;
        text-align: center;
        padding: 15px;
    }
    div[data-testid="stImage"] img {
        max-width: 100% !important;
        height: auto !important;
    }

    .card-content h1 {
        color: #fff;
        font-size: 1.25rem;
        margin: 0.3rem 0 0.3rem 0;
    }
    .card-content .desc {
        color: #8b949e;
        font-size: 0.85rem;
        margin: 0 0 0.5rem 0;
        line-height: 1.4;
    }

    .launcher-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 600;
        margin-right: 0.3rem;
        margin-bottom: 0.3rem;
    }
    .badge-noai { background: #23863622; color: #7ee787; border: 1px solid #23863644; }
    .badge-ready { background: #d2991d22; color: #d2991d; border: 1px solid #d2991d44; }
    .badge-db { background: #1f6feb22; color: #58a6ff; border: 1px solid #1f6feb44; }

    div[data-testid="stButton"] button {
        background: #ff6b35 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 14px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        width: 100% !important;
        margin-top: 0.4rem;
    }
    div[data-testid="stButton"] button:hover { background: #e85d2c !important; }

    .footer {
        text-align: center;
        padding: 1.5rem;
        color: #484f58;
        font-size: 0.8rem;
        border-top: 1px solid #30363d;
        margin-top: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ========== HERO ==========
st.markdown('<div class="hero"><div class="hero-inner">', unsafe_allow_html=True)
col_spacer_l, col_lottie, col_text, col_spacer_r = st.columns([2, 1, 3, 2], vertical_alignment="center")
with col_lottie:
    if lottie_hero:
        st_lottie(lottie_hero, height=180, width=180, key="hero_lottie")
with col_text:
    st.markdown("""
        <h1>QA Netting Bunga RAK</h1>
        <p>Validasi hasil netting bunga RAK (gl_rak_func_EOM) langsung dari JSON detail_harian</p>
    """, unsafe_allow_html=True)
st.markdown('</div></div>', unsafe_allow_html=True)

# ========== LAUNCHER GRID ==========
col1, col2 = st.columns(2, gap="medium")

with col1:
    st.markdown('<div class="card-wrapper">', unsafe_allow_html=True)
    c_icon, c_text = st.columns([1, 3])
    with c_icon:
        st.image(ASSET_POSTGRES, width=220)
    with c_text:
        st.markdown('<div class="card-content">', unsafe_allow_html=True)
        st.markdown('<h1>Validasi via Database</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="desc">Masukin konfig DB (read-only), pilih cabang + periode, '
            'sistem ambil detail_harian dari gl_hist_rakrate otomatis, render data grid, '
            'dan bandingin hasil hitung ulang netting vs net_bunga_rak yang tersimpan.</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<span class="launcher-badge badge-db">🗄️ Perlu Akses DB</span>'
            '<span class="launcher-badge badge-ready">✅ Ready</span>',
            unsafe_allow_html=True,
        )
        if st.button("🚀 Buka Validasi via Database", key="btn_db_home", width="stretch"):
            st.switch_page("pages/1_Validasi_via_Database.py")
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card-wrapper">', unsafe_allow_html=True)
    c_icon, c_text = st.columns([1, 3])
    with c_icon:
        st.image(ASSET_JSON, width=220)
    with c_text:
        st.markdown('<div class="card-content">', unsafe_allow_html=True)
        st.markdown('<h1>Validasi via Paste JSON</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="desc">Gak perlu konfig DB - tinggal paste value JSON detail_harian '
            '(hasil copy dari query manual/DBeaver/pgAdmin dsb), langsung jadi data grid '
            'dan dihitung netting-nya.</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<span class="launcher-badge badge-noai">🔧 No DB</span>'
            '<span class="launcher-badge badge-ready">✅ Ready</span>',
            unsafe_allow_html=True,
        )
        if st.button("🚀 Buka Validasi via Paste JSON", key="btn_json_home", width="stretch"):
            st.switch_page("pages/2_Validasi_via_Paste_JSON.py")
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("""
<div class="footer">
    QA Netting Bunga RAK &middot; dibangun buat validasi gl_rak_func_EOM &middot; Streamlit
</div>
""", unsafe_allow_html=True)
