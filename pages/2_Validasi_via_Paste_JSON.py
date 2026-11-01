import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
import streamlit as st
import pandas as pd
from openpyxl.styles import Font

from core.netting import (
    parse_detail_harian_input, to_dataframe, compute_netting, fmt_rupiah,
    classify_posisi_from_code, pusat_cabang_title, DetailHarianError,
)

ASSET_JSON = "assets/json.png"

st.set_page_config(page_title="Validasi via Paste JSON - QA Netting Bunga RAK", page_icon=ASSET_JSON, layout="wide")

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
    st.image(ASSET_JSON, width=100)
with col_title:
    st.title("Validasi Netting Bunga RAK — via Paste JSON")
st.caption("Gak perlu konfig DB. Paste value kolom detail_harian (array JSON) atau 1 baris penuh gl_hist_rakrate yang ada field detail_harian-nya.")

if st.button("⬅️ Kembali ke Home"):
    st.switch_page("app.py")

PLACEHOLDER = (
    '[{"tgl_efektif": "2026-09-15", "coa_posisi": "297010001", '
    '"coa_name": "ANTAR KANTOR AKTIVA - INDUK", "rate_tahunan": 0.6, '
    '"rate_harian": 0.001644, "cbal_posisi": 250000000, "bunga": 4110}, ...]'
)

if "raw_json_input" not in st.session_state:
    st.session_state.raw_json_input = ""


def _clear_input():
    st.session_state.raw_json_input = ""
    st.session_state.pop("parsed_rows", None)
    st.session_state.pop("parsed_meta", None)


st.text_area("Paste JSON detail_harian di sini", height=260, placeholder=PLACEHOLDER, key="raw_json_input")

col_clear, col_exec = st.columns(2)
with col_clear:
    st.button("🗑️ Clear", on_click=_clear_input, width="stretch")
with col_exec:
    execute_clicked = st.button("▶️ Execute", type="primary", width="stretch")

net_bunga_rak_manual = st.number_input(
    "net_bunga_rak dari sistem (opsional, buat dibandingin)",
    value=0, step=1, format="%d",
    help="Kosongkan/biarkan 0 kalau gak punya angka pembanding dari sistem.",
)
ada_pembanding = st.checkbox("Ada angka net_bunga_rak dari sistem buat dibandingkan", value=False)

if execute_clicked:
    if not st.session_state.raw_json_input.strip():
        st.error("JSON masih kosong - paste dulu sebelum Execute.")
        st.session_state.pop("parsed_rows", None)
    else:
        try:
            rows, meta = parse_detail_harian_input(st.session_state.raw_json_input)
            st.session_state["parsed_rows"] = rows
            st.session_state["parsed_meta"] = meta
        except DetailHarianError as e:
            st.error(f"JSON gak bisa diproses: {e}")
            st.session_state.pop("parsed_rows", None)

if "parsed_rows" not in st.session_state:
    st.info("Paste JSON di atas lalu klik **Execute** buat generate data grid.")
    st.stop()

rows = st.session_state["parsed_rows"]
meta = st.session_state["parsed_meta"]
df_detail = to_dataframe(rows)

if meta.get("net_bunga_rak") is not None and not ada_pembanding:
    st.info(f"JSON yang kamu paste ada field 'net_bunga_rak' = {fmt_rupiah(meta['net_bunga_rak'])}. Centang di atas kalau mau pake ini sebagai pembanding.")

# ---- Deteksi brncd (dari field top-level ATAU kolom per-baris) biar jelas ini Pusat thd cabang mana ----
brncd_detected = meta.get("brncd")
if not brncd_detected and "brncd" in df_detail.columns:
    non_null = df_detail["brncd"].dropna()
    if not non_null.empty:
        brncd_detected = non_null.iloc[0]
st.markdown(f"#### 🏢 {pusat_cabang_title(brncd_detected)}")

if "coa_posisi" not in df_detail.columns:
    st.error("Data gak punya kolom 'coa_posisi' - gak bisa ditentukan sisi Aktiva/Pasiva-nya.")
    st.stop()

# ---- Daftar unique COA + klasifikasi Aktiva/Pasiva (hardcode 3 digit awal kode: 297=Aktiva, 397=Pasiva) ----
has_name = "coa_name" in df_detail.columns
if has_name:
    unique_coa = df_detail[["coa_posisi", "coa_name"]].drop_duplicates().sort_values("coa_posisi")
else:
    unique_coa = pd.DataFrame({"coa_posisi": sorted(df_detail["coa_posisi"].dropna().unique())})
    unique_coa["coa_name"] = ""

unique_coa["posisi_auto"] = unique_coa["coa_posisi"].apply(classify_posisi_from_code)
unique_coa["label"] = unique_coa.apply(
    lambda r: f"{r['coa_posisi']} - {r['coa_name']}" if r["coa_name"] else str(r["coa_posisi"]), axis=1
)

st.markdown("### 🧭 Filter COA")
st.caption(
    "Pilih **All** buat lihat semua baris sekaligus hitung netting (butuh KEDUA sisi Aktiva & Pasiva). "
    "Pilih salah satu COA buat cuma lihat baris sisi itu - netting otomatis 0 karena cuma 1 sisi yang kelihatan."
)
filter_options = ["All"] + unique_coa["label"].tolist()
filter_choice = st.selectbox("Filter", filter_options)

selected_row = None
if filter_choice == "All":
    df_view = df_detail.copy()
    unresolved = unique_coa[unique_coa["posisi_auto"].isna()]
    if not unresolved.empty:
        st.warning(
            "Kode COA berikut gak diawali 297/397, jadi gak bisa diklasifikasi Aktiva/Pasiva: "
            + ", ".join(unresolved["label"].tolist())
            + ". Netting gak dihitung sampai ini jelas."
        )
        netting_mode = "unresolved"
    else:
        aktiva_codes = unique_coa.loc[unique_coa["posisi_auto"] == "Aktiva", "coa_posisi"].tolist()
        result = compute_netting(df_detail, aktiva_codes)
        netting_mode = "all"
else:
    selected_row = unique_coa[unique_coa["label"] == filter_choice].iloc[0]
    selected_code = selected_row["coa_posisi"]
    df_view = df_detail[df_detail["coa_posisi"] == selected_code].copy()
    netting_mode = "single"

# ---- Data mentah (numerik, buat Excel) vs data tampilan (Rupiah, buat layar) ----
if netting_mode == "all":
    df_raw = result["df_with_posisi"].copy()
else:
    df_raw = df_view.copy()
    df_raw["posisi"] = df_raw["coa_posisi"].apply(classify_posisi_from_code)

st.markdown("### 📊 Data Grid — detail_harian")
df_display = df_raw.copy()
if "bunga" in df_display.columns:
    df_display["bunga"] = df_display["bunga"].apply(fmt_rupiah)
if "cbal_posisi" in df_display.columns:
    df_display["cbal_posisi"] = df_display["cbal_posisi"].apply(fmt_rupiah)
st.dataframe(df_display, width="stretch", hide_index=True)

st.markdown("### 🧮 Hasil Netting")
if netting_mode == "all":
    total_aktiva, total_pasiva, netto = result["total_aktiva"], result["total_pasiva"], result["netto"]
elif netting_mode == "single":
    filtered_sum = float(df_view["bunga"].sum()) if "bunga" in df_view.columns else 0.0
    selected_posisi = classify_posisi_from_code(selected_row.get("coa_posisi"))
    total_aktiva = filtered_sum if selected_posisi == "Aktiva" else 0.0
    total_pasiva = filtered_sum if selected_posisi == "Pasiva" else 0.0
    netto = 0.0
    st.caption("ℹ️ Netting hanya dihitung ketika filter = **All** (butuh kedua sisi). Filter saat ini cuma menampilkan 1 sisi, jadi Netto = 0.")
else:  # unresolved
    total_aktiva = total_pasiva = netto = 0.0
    st.caption("⚠️ Posisi Aktiva/Pasiva belum bisa dipastikan otomatis - lihat peringatan di atas. Netto = 0 sementara.")

m1, m2, m3, m4 = st.columns(4)
m1.markdown(f'<div class="metric-box"><div class="label">Total Bunga Aktiva</div><div class="value">{fmt_rupiah(total_aktiva)}</div></div>', unsafe_allow_html=True)
m2.markdown(f'<div class="metric-box"><div class="label">Total Bunga Pasiva</div><div class="value">{fmt_rupiah(total_pasiva)}</div></div>', unsafe_allow_html=True)
m3.markdown(f'<div class="metric-box"><div class="label">Netto (Hitung Ulang)</div><div class="value">{fmt_rupiah(netto)}</div></div>', unsafe_allow_html=True)

pembanding_value = net_bunga_rak_manual if ada_pembanding else None

if pembanding_value is not None and netting_mode == "all":
    selisih = float(netto) - float(pembanding_value)
    match = abs(selisih) < 1
    cls = "match-ok" if match else "match-bad"
    label = "✅ MATCH" if match else "❌ MISMATCH"
    m4.markdown(
        f'<div class="metric-box"><div class="label">net_bunga_rak (Input)</div>'
        f'<div class="value">{fmt_rupiah(pembanding_value)}</div>'
        f'<div class="{cls}" style="font-weight:700;margin-top:4px">{label}</div></div>',
        unsafe_allow_html=True,
    )
    if not match:
        st.error(f"⚠️ Selisih {fmt_rupiah(selisih)} antara hasil hitung ulang vs angka pembanding.")
    else:
        st.success("Hasil hitung ulang netting SAMA PERSIS dengan angka pembanding. ✅")
else:
    m4.markdown('<div class="metric-box"><div class="label">net_bunga_rak (Input)</div><div class="value">-</div></div>', unsafe_allow_html=True)

if netting_mode == "all":
    with st.expander("📋 Breakdown per COA"):
        st.dataframe(result["breakdown"], width="stretch", hide_index=True)

# ---- Excel download (pake data mentah/numerik, bukan yang udah diformat Rupiah) ----
title_text = pusat_cabang_title(brncd_detected)
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    df_raw.to_excel(writer, sheet_name="detail_harian", index=False, startrow=2)
    ws_detail = writer.sheets["detail_harian"]
    ws_detail["A1"] = title_text
    ws_detail["A1"].font = Font(bold=True, size=12)

    if netting_mode == "all":
        result["breakdown"].to_excel(writer, sheet_name="breakdown", index=False, startrow=2)
        writer.sheets["breakdown"]["A1"] = title_text
        writer.sheets["breakdown"]["A1"].font = Font(bold=True, size=12)

    pd.DataFrame([{
        "brncd": brncd_detected, "filter": filter_choice,
        "total_aktiva": total_aktiva, "total_pasiva": total_pasiva,
        "netto_hitung_ulang": netto, "net_bunga_rak_pembanding": pembanding_value,
    }]).to_excel(writer, sheet_name="ringkasan", index=False, startrow=2)
    writer.sheets["ringkasan"]["A1"] = title_text
    writer.sheets["ringkasan"]["A1"].font = Font(bold=True, size=12)

st.download_button(
    "📥 Download Excel",
    buffer.getvalue(),
    file_name="validasi_netting_paste_json.xlsx",
    width="stretch",
)
