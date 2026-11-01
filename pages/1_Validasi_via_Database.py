import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import io
import streamlit as st
import pandas as pd
from openpyxl.styles import Font

from core.db_connector import DatabaseManager
from core.netting import (
    parse_detail_harian_input, to_dataframe, compute_netting, fmt_rupiah,
    classify_posisi_from_code, pusat_cabang_title, DetailHarianError,
)

ASSET_POSTGRES = "assets/postgres.png"

st.set_page_config(page_title="Validasi via Database - QA Netting Bunga RAK", page_icon=ASSET_POSTGRES, layout="wide")

st.markdown("""
<style>
    .stButton > button { width: 100%; }
    .metric-box {
        background: #161b22; border: 1px solid #30363d; border-radius: 10px;
        padding: 0.9rem 1rem; text-align: center;
    }
    .metric-box .label { color: #8b949e; font-size: 0.78rem; margin-bottom: 0.2rem; }
    .metric-box .value { color: #fff; font-size: 1.3rem; font-weight: 700; }
    .match-ok { color: #7ee787 !important; }
    .match-bad { color: #ff6b6b !important; }
</style>
""", unsafe_allow_html=True)

col_icon, col_title = st.columns([1, 10])
with col_icon:
    st.image(ASSET_POSTGRES, width=100)
with col_title:
    st.title("Validasi Netting Bunga RAK — via Database")
st.caption("Ambil detail_harian langsung dari gl_hist_rakrate (read-only), hitung ulang netting-nya, bandingin sama net_bunga_rak yang tersimpan.")

if st.button("⬅️ Kembali ke Home"):
    st.switch_page("app.py")

# ========== SESSION STATE ==========
if "db_manager" not in st.session_state:
    st.session_state.db_manager = DatabaseManager()
if "connection_status" not in st.session_state:
    st.session_state.connection_status = False
if "db_config" not in st.session_state:
    config_file = ".streamlit/db_config.json"
    default_cfg = {"type": "postgresql", "host": "localhost", "port": 5432, "database": "", "user": "", "password": ""}
    try:
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                st.session_state.db_config = json.load(f)
        else:
            st.session_state.db_config = default_cfg
    except Exception:
        st.session_state.db_config = default_cfg

# ========== SIDEBAR: KONFIG DB ==========
with st.sidebar:
    st.header("🔌 Konfigurasi Database")
    st.caption("Koneksi SELALU read-only - tool ini gak pernah nulis ke DB.")

    db_type = st.selectbox("Tipe Database", ["PostgreSQL", "MySQL/MariaDB"],
                            index=0 if st.session_state.db_config.get("type", "postgresql") == "postgresql" else 1)
    host = st.text_input("Host", value=st.session_state.db_config.get("host", "localhost"))
    col_a, col_b = st.columns(2)
    with col_a:
        port = st.number_input("Port", value=int(st.session_state.db_config.get("port", 5432)), step=1)
    with col_b:
        database = st.text_input("Database", value=st.session_state.db_config.get("database", ""))
    user = st.text_input("Username", value=st.session_state.db_config.get("user", ""))
    password = st.text_input("Password", value=st.session_state.db_config.get("password", ""), type="password")

    st.divider()
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        connect_btn = st.button("🔌 Connect", type="primary", width="stretch")
    with col_c2:
        disconnect_btn = st.button("🔌 Disconnect", width="stretch", disabled=not st.session_state.connection_status)

    if connect_btn:
        db_config = {
            "type": "postgresql" if db_type == "PostgreSQL" else "mysql",
            "host": host, "port": port, "database": database, "user": user, "password": password,
        }
        st.session_state.db_config = db_config
        os.makedirs(".streamlit", exist_ok=True)
        with open(".streamlit/db_config.json", "w") as f:
            json.dump(db_config, f)
        with st.spinner("Menghubungkan ke database..."):
            ok, msg = st.session_state.db_manager.connect(db_config)
        if ok:
            st.session_state.connection_status = True
            st.success(msg)
            st.balloons()
        else:
            st.session_state.connection_status = False
            st.error(msg)

    if disconnect_btn:
        st.session_state.db_manager.disconnect()
        st.session_state.connection_status = False
        st.info("Terputus dari database.")

    if st.session_state.connection_status:
        st.success("Status: Terhubung ✅")
    else:
        st.warning("Status: Belum terhubung")

# ========== MAIN AREA ==========
if not st.session_state.connection_status:
    st.info("👈 Isi konfigurasi database di sidebar dan klik **Connect** dulu.")
    st.stop()

db: DatabaseManager = st.session_state.db_manager

# ---- Ambil daftar cabang+periode yang tersedia ----
try:
    df_periode = db.query_df(
        "SELECT DISTINCT brncd, periode FROM gl_hist_rakrate ORDER BY periode DESC, brncd ASC"
    )
except Exception as e:
    st.error(f"Gagal ambil daftar cabang/periode dari gl_hist_rakrate: {e}")
    st.stop()

if df_periode.empty:
    st.warning("Belum ada baris di gl_hist_rakrate untuk database ini.")
    st.stop()

df_periode["label"] = df_periode["brncd"].astype(str) + " — " + df_periode["periode"].astype(str)
pilihan = st.selectbox("Pilih Cabang + Periode", df_periode["label"].tolist())
row_sel = df_periode[df_periode["label"] == pilihan].iloc[0]
brncd_sel, periode_sel = row_sel["brncd"], row_sel["periode"]

if st.button("📥 Ambil & Validasi", type="primary"):
    st.session_state["_db_fetch"] = (brncd_sel, periode_sel)

if "_db_fetch" not in st.session_state:
    st.stop()

brncd_q, periode_q = st.session_state["_db_fetch"]

try:
    df_row = db.query_df(
        """
        SELECT id, brncd, periode, coa_posisi_hasil, crdr, year_interest,
               detail_harian, net_bunga_rak, created_at
        FROM gl_hist_rakrate
        WHERE brncd = %(brncd)s AND periode = %(periode)s
        """,
        {"brncd": brncd_q, "periode": periode_q},
    )
except Exception as e:
    st.error(f"Query gl_hist_rakrate gagal: {e}")
    st.stop()

if df_row.empty:
    st.warning("Baris untuk cabang+periode ini gak ketemu (mungkin udah beda sejak dipilih).")
    st.stop()

row = df_row.iloc[0]
net_bunga_rak_sistem = row.get("net_bunga_rak")

st.subheader(f"📌 {pusat_cabang_title(brncd_q)} — Periode {periode_q}")
c1, c2, c3 = st.columns(3)
c1.markdown(f'<div class="metric-box"><div class="label">coa_posisi_hasil (hari terakhir)</div><div class="value">{row.get("coa_posisi_hasil")}</div></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="metric-box"><div class="label">crdr (hari terakhir)</div><div class="value">{row.get("crdr")}</div></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="metric-box"><div class="label">year_interest</div><div class="value">{row.get("year_interest")}%</div></div>', unsafe_allow_html=True)

try:
    rows, _meta = parse_detail_harian_input(row["detail_harian"])
    df_detail = to_dataframe(rows)
except DetailHarianError as e:
    st.error(f"detail_harian gak bisa diparse: {e}")
    st.stop()

# ---- Klasifikasi Aktiva/Pasiva (hardcode 3 digit awal kode: 297=Aktiva, 397=Pasiva) ----
unique_codes = sorted(df_detail["coa_posisi"].dropna().unique().tolist()) if "coa_posisi" in df_detail.columns else []
posisi_map = {c: classify_posisi_from_code(c) for c in unique_codes}
unresolved_codes = [c for c, p in posisi_map.items() if p is None]

if unresolved_codes:
    st.warning(f"Kode COA berikut gak diawali 297/397, gak bisa diklasifikasi otomatis: {unresolved_codes}. Tentukan manual mana yang Aktiva:")
    default_aktiva = [c for c, p in posisi_map.items() if p == "Aktiva"]
    aktiva_codes = st.multiselect("Kode COA sisi Aktiva", unique_codes, default=default_aktiva)
else:
    aktiva_codes = [c for c, p in posisi_map.items() if p == "Aktiva"]

st.markdown("### 📊 Data Grid — detail_harian")
result = compute_netting(df_detail, aktiva_codes)
df_raw = result["df_with_posisi"].copy()
if "brncd" not in df_raw.columns:
    df_raw.insert(0, "brncd", brncd_q)
df_display = df_raw.copy()
if "bunga" in df_display.columns:
    df_display["bunga"] = df_display["bunga"].apply(fmt_rupiah)
if "cbal_posisi" in df_display.columns:
    df_display["cbal_posisi"] = df_display["cbal_posisi"].apply(fmt_rupiah)
st.dataframe(df_display, width="stretch", hide_index=True)

st.markdown("### 🧮 Hasil Netting")
m1, m2, m3, m4 = st.columns(4)
m1.markdown(f'<div class="metric-box"><div class="label">Total Bunga Aktiva</div><div class="value">{fmt_rupiah(result["total_aktiva"])}</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="metric-box"><div class="label">Total Bunga Pasiva</div><div class="value">{fmt_rupiah(result["total_pasiva"])}</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="metric-box"><div class="label">Netto (Hitung Ulang)</div><div class="value">{fmt_rupiah(result["netto"])}</div></div>', unsafe_allow_html=True)

if net_bunga_rak_sistem is not None:
    selisih = float(result["netto"]) - float(net_bunga_rak_sistem)
    match = abs(selisih) < 1
    cls = "match-ok" if match else "match-bad"
    label = "✅ MATCH" if match else "❌ MISMATCH"
    m4.markdown(
        f'<div class="metric-box"><div class="label">net_bunga_rak (Sistem)</div>'
        f'<div class="value">{fmt_rupiah(net_bunga_rak_sistem)}</div>'
        f'<div class="{cls}" style="font-weight:700;margin-top:4px">{label}</div></div>',
        unsafe_allow_html=True,
    )
    if not match:
        st.error(f"⚠️ Selisih {fmt_rupiah(selisih)} antara hasil hitung ulang vs net_bunga_rak tersimpan di sistem. Cek logic gl_rak_func_EOM.")
    else:
        st.success("Hasil hitung ulang netting SAMA PERSIS dengan net_bunga_rak yang tersimpan sistem. ✅")
else:
    m4.markdown('<div class="metric-box"><div class="label">net_bunga_rak (Sistem)</div><div class="value">-</div></div>', unsafe_allow_html=True)

with st.expander("📋 Breakdown per COA"):
    st.dataframe(result["breakdown"], width="stretch", hide_index=True)

# ---- Excel download ----
title_text = f"{pusat_cabang_title(brncd_q)} — Periode {periode_q}"
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    df_raw.to_excel(writer, sheet_name="detail_harian", index=False, startrow=2)
    writer.sheets["detail_harian"]["A1"] = title_text
    writer.sheets["detail_harian"]["A1"].font = Font(bold=True, size=12)

    result["breakdown"].to_excel(writer, sheet_name="breakdown", index=False, startrow=2)
    writer.sheets["breakdown"]["A1"] = title_text
    writer.sheets["breakdown"]["A1"].font = Font(bold=True, size=12)

    pd.DataFrame([{
        "brncd": brncd_q, "periode": periode_q,
        "total_aktiva": result["total_aktiva"], "total_pasiva": result["total_pasiva"],
        "netto_hitung_ulang": result["netto"], "net_bunga_rak_sistem": net_bunga_rak_sistem,
    }]).to_excel(writer, sheet_name="ringkasan", index=False, startrow=2)
    writer.sheets["ringkasan"]["A1"] = title_text
    writer.sheets["ringkasan"]["A1"].font = Font(bold=True, size=12)

st.download_button(
    "📥 Download Excel",
    buffer.getvalue(),
    file_name=f"validasi_netting_{brncd_q}_{periode_q}.xlsx",
    width="stretch",
)
