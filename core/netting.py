"""
Logic inti validasi netting bunga RAK - dipakai BARENG oleh kedua launcher
(mode Database maupun mode Paste JSON) biar hasil hitungannya konsisten,
gak ada 2 rumus beda di 2 tempat.

Sumber rumus: FSD gl_rak_func_EOD/EOM & bunga_rak_erd.dbml (TEMUAN #66) -
net_bunga_rak = SUM(bunga) sisi Aktiva - SUM(bunga) sisi Pasiva. Posisi
Aktiva/Pasiva ditentukan dari 3 digit awal kode COA (297=Aktiva, 397=Pasiva -
hardcode sesuai konvensi penomoran COA RAK, permintaan user 2026-10-20).
"""
from __future__ import annotations

import json
import pandas as pd

EXPECTED_COLUMNS = [
    "brncd",
    "tgl_efektif",
    "coa_posisi",
    "coa_name",
    "rate_tahunan",
    "rate_harian",
    "cbal_posisi",
    "bunga",
]


class DetailHarianError(Exception):
    pass


def parse_detail_harian_input(raw) -> tuple[list[dict], dict]:
    """
    Terima input mentah (string JSON ATAU object Python yang udah ke-parse
    psycopg2/JSONB), kembalikan (list_hari, meta).

    Bentuk yang didukung:
      1. Array murni: [ {...}, {...} ]  -> ini bentuk asli kolom detail_harian
      2. Object pembungkus: {"brncd":..,"periode":..,"detail_harian":[...],
         "net_bunga_rak":..} -> kalau user paste hasil query 1 baris penuh
         (bukan cuma kolom detail_harian-nya doang)
    """
    data = raw
    if isinstance(raw, (str, bytes)):
        raw_str = raw.strip()
        if not raw_str:
            raise DetailHarianError("Input JSON kosong.")
        try:
            data = json.loads(raw_str)
        except json.JSONDecodeError as e:
            raise DetailHarianError(f"JSON tidak valid: {e}")

    meta: dict = {}
    if isinstance(data, dict):
        meta = {k: v for k, v in data.items() if k != "detail_harian"}
        if "detail_harian" not in data:
            raise DetailHarianError(
                "Object JSON ini gak punya field 'detail_harian'. "
                "Paste salah satu: array detail_harian langsung, atau seluruh "
                "baris gl_hist_rakrate yang isinya ada field 'detail_harian'."
            )
        rows = data["detail_harian"]
    elif isinstance(data, list):
        rows = data
    else:
        raise DetailHarianError("Bentuk JSON gak dikenali (harus array atau object).")

    if not isinstance(rows, list) or len(rows) == 0:
        raise DetailHarianError("detail_harian kosong/bukan array.")
    if not all(isinstance(r, dict) for r in rows):
        raise DetailHarianError("Setiap elemen detail_harian harus berupa object.")

    return rows, meta


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Taruh kolom yang dikenal duluan (urutan rapi), sisanya (kalau ada kolom
    # tambahan yang gak terduga) tetap ditampilkan di belakang - JANGAN di-drop
    # diam-diam, biar QA sadar kalau ada field baru yang belum didukung tool ini.
    known = [c for c in EXPECTED_COLUMNS if c in df.columns]
    rest = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    df = df[known + rest]
    if "tgl_efektif" in df.columns:
        df = df.sort_values("tgl_efektif", kind="stable").reset_index(drop=True)
    return df


def compute_netting(df: pd.DataFrame, aktiva_coa_posisi) -> dict:
    """
    aktiva_coa_posisi: nilai coa_posisi yang dianggap sisi AKTIVA (bisa 1 value
    atau list/set of values kalau ada lebih dari 1 kode yang masuk kelompok
    Aktiva - jaga-jaga, walau normalnya cuma 1 vs 1).
    Semua coa_posisi LAIN yang muncul di data otomatis dianggap sisi PASIVA.
    """
    if "coa_posisi" not in df.columns or "bunga" not in df.columns:
        raise DetailHarianError("Data gak punya kolom 'coa_posisi' dan/atau 'bunga' - gak bisa dihitung netting-nya.")

    aktiva_set = {aktiva_coa_posisi} if not isinstance(aktiva_coa_posisi, (list, set, tuple)) else set(aktiva_coa_posisi)
    df = df.copy()
    df["posisi"] = df["coa_posisi"].apply(lambda c: "Aktiva" if c in aktiva_set else "Pasiva")

    total_aktiva = float(df.loc[df["posisi"] == "Aktiva", "bunga"].sum())
    total_pasiva = float(df.loc[df["posisi"] == "Pasiva", "bunga"].sum())
    netto = total_aktiva - total_pasiva

    breakdown = (
        df.groupby(["coa_posisi", "posisi"], dropna=False)
        .agg(jumlah_hari=("bunga", "count"), total_bunga=("bunga", "sum"))
        .reset_index()
        .sort_values("posisi")
    )

    return {
        "df_with_posisi": df,
        "total_aktiva": total_aktiva,
        "total_pasiva": total_pasiva,
        "netto": netto,
        "breakdown": breakdown,
    }


def classify_posisi_from_code(coa_posisi) -> str | None:
    """
    Hardcode sesuai konvensi penomoran COA RAK (permintaan user eksplisit,
    2026-10-20): 3 digit AWAL kode COA - '297' = Aktiva, '397' = Pasiva.
    Dipakai KONSISTEN di kedua mode (Database & Paste JSON).
    Return None kalau kodenya gak diawali 297/397 - JANGAN ditebak lebih jauh,
    biar ketahuan ada data COA RAK yang di luar konvensi biasa.
    """
    if coa_posisi is None:
        return None
    s = str(coa_posisi).strip()
    if s.startswith("297"):
        return "Aktiva"
    if s.startswith("397"):
        return "Pasiva"
    return None


def fmt_rupiah(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if v < 0 else ""
    return f"{sign}Rp{abs(v):,.0f}".replace(",", ".")


def pusat_cabang_title(brncd, pusat_code: str = "370") -> str:
    """Label standar 'Kantor Pusat (370) -> Cabang xxx', dipakai di UI & header Excel."""
    if not brncd:
        return f"Kantor Pusat ({pusat_code}) → Cabang (?)"
    return f"Kantor Pusat ({pusat_code}) → Cabang {brncd}"
