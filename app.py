from __future__ import annotations

import io
import base64
import hashlib
import hmac
import json
import re
import sqlite3
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="한살림생산자연합회 자금현황",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SHEET_INPUT = "01_자금현황_입력"
SHEET_SUMMARY = "02_월별요약_Looker"
SHEET_FLOW = "03_자금흐름_Looker"
SHEET_POINTS = "09_주요 포인트"
SYNC_SHEETS = (SHEET_INPUT, SHEET_SUMMARY, SHEET_FLOW)
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "fund_data.db"
GITHUB_API = "https://api.github.com"

GREEN = "#176B4B"
GREEN_2 = "#3E8E6A"
MINT = "#EAF5EF"
ORANGE = "#D9852B"
RED = "#C94A4A"
BLUE = "#3979A9"
INK = "#17251E"
MUTED = "#55665D"


st.markdown(
    """
    <style>
    html, body, [class*="css"] {font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;}
    .stApp {background:#F5F6F8; color:#20242A;}
    .block-container {padding:1rem 1.25rem 2rem; max-width:1540px;}
    h1 {font-size:2rem !important; line-height:1.25 !important; color:#143F2D !important; letter-spacing:-.03em;}
    h2, h3 {color:#183E2E !important;}
    p, label, .stCaption {font-size:1rem !important; color:#3E5147;}
    [data-testid="stSidebar"] {background:#28388C;}
    [data-testid="stSidebar"] * {color:#FFFFFF !important;}
    [data-testid="stSidebar"] [data-baseweb="select"] * {color:#17251E !important;}
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {background:#25533F; border:1px dashed #9AC3AE;}
    [data-testid="stDataFrame"] {border:1px solid #D7DADF; border-radius:4px; overflow:hidden;}
    .hero {background:#28388C; padding:.72rem 1.05rem; border-radius:6px; color:white; margin-bottom:.8rem;}
    .hero h1 {color:white !important; margin:0; font-size:1.55rem !important;}
    .hero p {color:#E8ECFF !important; margin:.18rem 0 0; font-size:.95rem !important;}
    .period-pill {display:inline-block; margin-top:.85rem; padding:.38rem .75rem; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3); border-radius:999px; font-weight:800;}
    .section {background:#28388C;color:#fff;margin:.55rem 0 .25rem;padding:.34rem .72rem;border-radius:5px;font-size:1.08rem;font-weight:900;}
    .section:before {display:none;}
    .panel {background:#FFF; border:1px solid #D7DADF; border-radius:4px; padding:.7rem; margin-bottom:.65rem; min-height:100%;}
    .panel-title {font-size:1.12rem; font-weight:900; color:#173F2E; margin-bottom:.15rem;}
    .panel-sub {font-size:.92rem; color:#6A786F; margin-bottom:.4rem;}
    .point {background:#F0F0F0; padding:.46rem .58rem; margin:.32rem 0; font-size:.98rem; line-height:1.45; color:#343940;}
    .kpi-grid{display:grid;grid-template-columns:1fr .22fr 1fr .22fr 1fr .22fr 1fr .22fr 1fr;gap:8px;align-items:center;margin:.45rem 0 .8rem}
    .op{text-align:center;font-size:1.55rem;font-weight:900;color:#222}
    .kpi{background:#fff;border:4px solid var(--c);border-radius:5px;text-align:center;overflow:hidden;min-height:128px}
    .kpi-title{font-size:1.02rem;font-weight:900;padding:.46rem .2rem .15rem;color:#191D23}
    .kpi-main{font-size:1.78rem;padding:.3rem .15rem .22rem;color:#3E434A;white-space:nowrap}
    .kpi-main small{font-size:.72rem;margin-left:.28rem}
    .kpi-sub{background:var(--bg);padding:.36rem .15rem;font-size:.88rem;color:#343940;white-space:nowrap}
    .simple-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:.88rem}
    .simple-table th{background:#E7EEF9;padding:.42rem .48rem;text-align:right;white-space:nowrap}.simple-table th:first-child{text-align:left}
    .simple-table td{padding:.38rem .48rem;border-bottom:1px solid #ECEDEF;text-align:right;white-space:nowrap}.simple-table td:first-child{text-align:left;white-space:nowrap;overflow-wrap:normal}
    .simple-table tfoot td{font-weight:900;border-top:2px solid #C9CDD3;border-bottom:0}
    .simple-table .col-item{width:auto}.simple-table .col-money{width:42%}.simple-table .col-share{width:22%}
    .table-frame{min-height:350px;background:#fff;border:1px solid #E1E4E8;border-radius:4px;overflow:hidden}
    .table-frame.compact{min-height:255px}
    @media(max-width:1000px){.kpi-grid{grid-template-columns:1fr}.op{height:18px;line-height:18px}.block-container{padding:.6rem}}
    .empty {background:#F9FBFA; border:1px dashed #9BB1A4; border-radius:14px; padding:1.35rem; color:#566A5F; font-size:1rem;}
    .upload-welcome {background:#FFFFFF; border:2px dashed #8EB09D; border-radius:20px; padding:2.2rem; text-align:center; margin-top:1rem;}
    .status-good {display:inline-block; background:#DFF2E7; color:#176B4B; padding:.35rem .7rem; border-radius:999px; font-weight:800;}
    </style>
    """,
    unsafe_allow_html=True,
)


def norm(value: object) -> str:
    return re.sub(r"[\s_()\[\]·/\\-]+", "", str(value)).lower()


def find_col(df: pd.DataFrame, names: Iterable[str], required: bool = True) -> str | None:
    mapped = {norm(c): c for c in df.columns}
    for name in names:
        if norm(name) in mapped:
            return mapped[norm(name)]
    for name in names:
        key = norm(name)
        for normalized, original in mapped.items():
            if key and (key in normalized or normalized in key):
                return original
    if required:
        raise ValueError(f"필요한 열을 찾을 수 없습니다: {', '.join(names)}")
    return None


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    # 엑셀 양식에 같은 제목의 열이 반복되어도 저장·복원 단계가 멈추지 않게 한다.
    return df.loc[:, ~df.columns.duplicated()].copy()


def frame_from_table_json(raw: bytes) -> pd.DataFrame:
    """pandas table 스키마보다 실제 레코드를 우선해 월별 자료를 안전하게 복원한다."""
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        frame = pd.DataFrame(payload["data"])
        frame = frame.drop(columns=["index"], errors="ignore")
        return clean_frame(frame)
    return clean_frame(pd.read_json(io.StringIO(raw.decode("utf-8")), orient="table"))


def init_storage() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS monthly_sheets (
            month_key TEXT NOT NULL, sheet_name TEXT NOT NULL, data_json TEXT NOT NULL,
            original_filename TEXT, updated_at TEXT NOT NULL,
            PRIMARY KEY (month_key, sheet_name))""")
        con.commit()


def secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def remote_storage_ready() -> bool:
    return bool(secret("GITHUB_TOKEN") and secret("GITHUB_DATA_REPO"))


def github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_request(method: str, path: str, **kwargs):
    response = requests.request(
        method,
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        timeout=30,
        **kwargs,
    )
    if response.status_code >= 400:
        detail = response.json().get("message", response.text) if response.content else "응답 없음"
        raise RuntimeError(f"비공개 저장소 연결 오류 ({response.status_code}): {detail}")
    return response


def month_key(value: object) -> str:
    label = month_label(value)
    match = re.search(r"(20\d{2}).*?(\d{1,2})", label)
    return f"{match.group(1)}-{int(match.group(2)):02d}" if match else label


def frame_for_month(df: pd.DataFrame, key: str) -> pd.DataFrame:
    col = find_col(df, ["기준월", "월", "년월", "기준년월"], required=False)
    if not col:
        return df.copy()
    return df[df[col].map(month_key) == key].copy()


def month_keys(df: pd.DataFrame) -> set[str]:
    col = find_col(df, ["기준월", "월", "년월", "기준년월"], required=False)
    if not col:
        return set()
    return {month_label(value) for value in df[col].dropna() if str(value).strip()}


def save_workbook_local(incoming: dict[str, pd.DataFrame], raw: bytes, filename: str) -> tuple[list[str], set[str]]:
    summary = incoming[SHEET_SUMMARY]
    uploaded_months = {month_key(v) for v in summary[find_col(summary, ["기준월", "월", "년월", "기준년월"])].dropna()}
    if not uploaded_months:
        raise ValueError("업로드 파일에서 저장할 기준월을 찾지 못했습니다.")
    now = datetime.now().isoformat(timespec="seconds")
    saved: list[str] = []
    with sqlite3.connect(DB_PATH) as con:
        for key in uploaded_months:
            for name in SYNC_SHEETS:
                if name not in incoming:
                    if name in (SHEET_SUMMARY, SHEET_FLOW):
                        raise ValueError(f"필수 시트가 없습니다: {name}")
                    continue
                frame = frame_for_month(incoming[name], key)
                if frame.empty and find_col(incoming[name], ["기준월", "월", "년월", "기준년월"], required=False):
                    continue
                payload = frame.to_json(orient="table", date_format="iso", force_ascii=False)
                con.execute("""INSERT OR REPLACE INTO monthly_sheets
                    (month_key, sheet_name, data_json, original_filename, updated_at)
                    VALUES (?, ?, ?, ?, ?)""", (key, name, payload, filename, now))
                saved.append(name)
        con.commit()
    safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", Path(filename).name)
    for key in uploaded_months:
        (UPLOAD_DIR / f"{key}_{safe_name}").write_bytes(raw)
    return saved, uploaded_months


def monthly_archive(incoming: dict[str, pd.DataFrame], raw: bytes, filename: str, key: str) -> bytes:
    buffer = io.BytesIO()
    meta = {
        "month_key": key,
        "original_filename": Path(filename).name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(meta, ensure_ascii=False))
        for name in SYNC_SHEETS:
            if name not in incoming:
                if name in (SHEET_SUMMARY, SHEET_FLOW):
                    raise ValueError(f"필수 시트가 없습니다: {name}")
                continue
            frame = frame_for_month(incoming[name], key)
            if frame.empty and find_col(incoming[name], ["기준월", "월", "년월", "기준년월"], required=False):
                continue
            archive.writestr(
                f"sheets/{name}.json",
                frame.to_json(orient="table", date_format="iso", force_ascii=False),
            )
        archive.writestr(f"original/{Path(filename).name}", raw)
    return buffer.getvalue()


def github_content(path: str) -> tuple[bytes | None, str | None]:
    repo = secret("GITHUB_DATA_REPO")
    response = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/{path}",
        headers=github_headers(),
        timeout=30,
    )
    if response.status_code == 404:
        return None, None
    if response.status_code >= 400:
        detail = response.json().get("message", response.text)
        raise RuntimeError(f"비공개 저장소 읽기 오류 ({response.status_code}): {detail}")
    payload = response.json()
    return base64.b64decode(payload["content"]), payload["sha"]


def save_workbook_remote(incoming: dict[str, pd.DataFrame], raw: bytes, filename: str) -> tuple[list[str], set[str]]:
    summary = incoming[SHEET_SUMMARY]
    col = find_col(summary, ["기준월", "월", "년월", "기준년월"])
    uploaded_months = {month_key(v) for v in summary[col].dropna()}
    if not uploaded_months:
        raise ValueError("업로드 파일에서 저장할 기준월을 찾지 못했습니다.")
    repo = secret("GITHUB_DATA_REPO")
    branch = secret("GITHUB_DATA_BRANCH", "main")
    for key in uploaded_months:
        path = f"months/{key}.zip"
        archive = monthly_archive(incoming, raw, filename, key)
        _, sha = github_content(path)
        body = {
            "message": f"{key} 자금현황 저장",
            "content": base64.b64encode(archive).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        github_request("PUT", f"/repos/{repo}/contents/{path}", json=body)
    load_remote_sheets.clear()
    return list(SYNC_SHEETS), uploaded_months


@st.cache_data(ttl=30, show_spinner=False)
def load_remote_sheets(repo: str, token_fingerprint: str) -> dict[str, pd.DataFrame]:
    del token_fingerprint
    response = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/months",
        headers=github_headers(),
        timeout=30,
    )
    if response.status_code == 404:
        return {}
    if response.status_code >= 400:
        detail = response.json().get("message", response.text)
        raise RuntimeError(f"비공개 저장소 읽기 오류 ({response.status_code}): {detail}")
    items = response.json()
    grouped: dict[str, list[pd.DataFrame]] = {}
    for item in sorted(items, key=lambda x: x["name"]):
        if item.get("type") != "file" or not item["name"].endswith(".zip"):
            continue
        archive_key = Path(item["name"]).stem
        raw, _ = github_content(item["path"])
        if not raw:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            archived_sheets: set[str] = set()
            for name in archive.namelist():
                if not name.startswith("sheets/") or not name.endswith(".json"):
                    continue
                sheet_name = Path(name).stem
                frame = frame_from_table_json(archive.read(name))
                # 월말 잔고 입력 시트는 반드시 해당 월의 행만 사용한다.
                # 과거 파일에 전체 엑셀이 들어 있었더라도 다른 달 잔고를 합산하지 않는다.
                if sheet_name == SHEET_INPUT:
                    frame = input_frame_for_month(frame, archive_key)
                    if frame.empty:
                        continue
                grouped.setdefault(sheet_name, []).append(frame)
                archived_sheets.add(sheet_name)
            # 과거 저장본에 세부 입력 시트가 빠졌어도 원본 엑셀에서 복원해 그래프 공백을 막는다.
            if SHEET_INPUT not in archived_sheets:
                restored_input = restore_input_from_original(archive, archive_key)
                if restored_input is not None and not restored_input.empty:
                    grouped.setdefault(SHEET_INPUT, []).append(restored_input)
    result: dict[str, pd.DataFrame] = {}
    for name, frames in grouped.items():
        columns = list(dict.fromkeys(col for frame in frames for col in frame.columns))
        result[name] = pd.concat([f.reindex(columns=columns) for f in frames], ignore_index=True)
    return result


def input_frame_for_month(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """월말 잔고 입력은 기준월이 확인된 행만 반환해 중복 누적을 원천 차단한다."""
    month_col = find_col(df, ["기준월", "월", "년월", "기준년월"], required=False)
    if not month_col:
        return pd.DataFrame(columns=df.columns)
    return df[df[month_col].map(month_key) == key].copy()


def restore_input_from_original(archive: zipfile.ZipFile, key: str) -> pd.DataFrame | None:
    """이전 월별 파일에 입력 시트 JSON이 없으면 원본에서 해당 월 행만 안전하게 복원한다."""
    original = next((name for name in archive.namelist() if name.startswith("original/") and not name.endswith("/")), None)
    if not original:
        return None
    try:
        original_input = load_workbook(archive.read(original)).get(SHEET_INPUT)
        if original_input is None:
            return None
        return input_frame_for_month(original_input, key)
    except Exception:
        return None


def load_saved_sheets() -> dict[str, pd.DataFrame]:
    if remote_storage_ready():
        token_hash = hashlib.sha256(secret("GITHUB_TOKEN").encode()).hexdigest()[:12]
        return load_remote_sheets(secret("GITHUB_DATA_REPO"), token_hash)
    return load_local_sheets()


def load_local_sheets() -> dict[str, pd.DataFrame]:
    init_storage()
    grouped: dict[str, list[pd.DataFrame]] = {}
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT sheet_name, data_json FROM monthly_sheets ORDER BY month_key").fetchall()
    for name, payload in rows:
        grouped.setdefault(name, []).append(pd.read_json(io.StringIO(payload), orient="table"))
    result = {}
    for name, frames in grouped.items():
        columns = list(dict.fromkeys(col for frame in frames for col in frame.columns))
        result[name] = pd.concat([f.reindex(columns=columns) for f in frames], ignore_index=True)
    return result


def backup_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if DB_PATH.exists(): archive.write(DB_PATH, "fund_data.db")
        for path in UPLOAD_DIR.glob("*"):
            if path.is_file(): archive.write(path, f"uploads/{path.name}")
    return buffer.getvalue()


def restore_backup(raw: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set(archive.namelist())
        if "fund_data.db" not in names:
            raise ValueError("올바른 대시보드 백업 파일이 아닙니다.")
        DB_PATH.write_bytes(archive.read("fund_data.db"))
        for name in names:
            if name.startswith("uploads/") and not name.endswith("/"):
                target = UPLOAD_DIR / Path(name).name
                target.write_bytes(archive.read(name))


@st.cache_data(show_spinner=False)
def load_workbook(raw: bytes) -> dict[str, pd.DataFrame]:
    book = pd.read_excel(io.BytesIO(raw), sheet_name=None)
    return {str(name).strip(): clean_frame(frame) for name, frame in book.items()}


def month_label(value: object) -> str:
    if pd.isna(value):
        return "미지정"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y년 %m월")
    match = re.search(r"(20\d{2})\D*(\d{1,2})", str(value))
    return f"{match.group(1)}년 {int(match.group(2)):02d}월" if match else str(value)


def money(value: object) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^0-9.\-]", "", str(value))
    return float(text) if text not in {"", "-", "."} else 0.0


def won(value: float, compact: bool = True) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if compact and value >= 100_000_000:
        return f"{sign}{value / 100_000_000:,.2f}억 원"
    if compact and value >= 10_000:
        return f"{sign}{value / 10_000:,.0f}만 원"
    return f"{sign}{value:,.0f}원"


def pick_metric(row: pd.Series, aliases: list[str]) -> float:
    mapped = {norm(c): c for c in row.index}
    for alias in aliases:
        if norm(alias) in mapped:
            return money(row[mapped[norm(alias)]])
    for alias in aliases:
        for normalized, original in mapped.items():
            if norm(alias) in normalized:
                return money(row[original])
    return 0.0


def filter_month(df: pd.DataFrame, selected: object) -> pd.DataFrame:
    month_col = find_col(df, ["기준월", "월", "년월", "기준년월"], required=False)
    if not month_col:
        return df.copy()
    exact = df[df[month_col].astype(str) == str(selected)].copy()
    if not exact.empty:
        return exact
    return df[df[month_col].map(month_label) == month_label(selected)].copy()


def has_actual_balance(summary: pd.DataFrame, selected: object) -> bool:
    """0원 템플릿은 건너뛰고 실제 값이 있는 가장 최근 기준월을 기본으로 선택한다."""
    rows = filter_month(summary, selected)
    if rows.empty:
        return False
    row = rows.iloc[-1]
    metrics = ["총유동자산", "유동자산", "총유동부채", "유동부채", "순자금", "운영가능자금"]
    return any(abs(pick_metric(row, [metric])) > 0 for metric in metrics)


def category_table(source: pd.DataFrame, selected: object, keywords: list[str]) -> pd.DataFrame:
    """열 이름·분류 위치가 조금 달라도 지정된 자금 항목만 안전하게 집계한다."""
    if source.empty:
        return pd.DataFrame(columns=["항목", "금액"])
    df = filter_month(source, selected)
    category_columns = [
        column for column in df.columns
        if norm(column) in {norm(name) for name in ["대분류", "자금구분", "분류", "유동자산구분", "구분"]}
    ]
    item_col = find_col(df, ["항목", "세부항목", "계정명", "내역", "예금명", "세부내역"], required=False)
    amount_col = find_col(df, ["금액", "잔액", "당월금액", "합계", "금액(원)"], required=False)
    if df.empty or not item_col or not amount_col:
        return pd.DataFrame(columns=["항목", "금액"])

    normalized_keywords = [norm(keyword) for keyword in keywords]
    if category_columns:
        # '대분류=보통예금, 구분=1'처럼 분류 열이 여러 개여도 모두 확인한다.
        labels = df[category_columns].fillna("").astype(str).apply(
            lambda row: " ".join(norm(value) for value in row), axis=1
        )
        mask = labels.apply(lambda label: any(keyword in label for keyword in normalized_keywords))
    else:
        # 분류 열이 없는 입력양식도 전체 행에서 항목명을 찾아 세부 그래프를 유지한다.
        row_text = df.fillna("").astype(str).apply(
            lambda row: " ".join(norm(value) for value in row), axis=1
        )
        mask = row_text.apply(lambda text: any(keyword in text for keyword in normalized_keywords))

    result = pd.DataFrame({
        "항목": df.loc[mask, item_col].fillna("미분류").astype(str).to_numpy(),
        "금액": df.loc[mask, amount_col].map(money).to_numpy(),
    })
    # 도넛·표에는 양수 잔액만 표시해 음수 또는 빈 값 때문에 차트가 깨지지 않도록 한다.
    result = result[result["금액"] > 0]
    if result.empty:
        return pd.DataFrame(columns=["항목", "금액"])
    return result.groupby("항목", as_index=False)["금액"].sum().sort_values("금액", ascending=False)


def display_deposit_labels(deposits: pd.DataFrame, selected: object) -> pd.DataFrame:
    """6월부터 변경된 작목기금 명칭을 보통예금 구성에 일관되게 표시한다."""
    shown = deposits.copy()
    if month_key(selected) >= "2026-06":
        shown["항목"] = shown["항목"].replace({"연수원수입": "작목기금"})
        shown = shown.groupby("항목", as_index=False)["금액"].sum().sort_values("금액", ascending=False)
    return shown


def restricted_fund_table(source: pd.DataFrame, selected: object) -> pd.DataFrame:
    """입력 시트에서 '용도제한여부'가 Y인 항목만 집계한다."""
    if source.empty:
        return pd.DataFrame(columns=["항목", "금액"])
    df = filter_month(source, selected)
    restricted_col = find_col(df, ["용도제한여부"], required=False)
    item_col = find_col(df, ["항목", "세부항목", "계정명", "내역", "예금명", "세부내역"], required=False)
    amount_col = find_col(df, ["금액", "잔액", "당월금액", "합계", "금액(원)"], required=False)
    if not restricted_col or not item_col or not amount_col:
        return pd.DataFrame(columns=["항목", "금액"])
    y_rows = df[df[restricted_col].astype(str).str.strip().str.upper().eq("Y")]
    result = pd.DataFrame({
        "항목": y_rows[item_col].fillna("미분류").astype(str).to_numpy(),
        "금액": y_rows[amount_col].map(money).to_numpy(),
    })
    result = result[result["금액"] != 0]
    return result.groupby("항목", as_index=False)["금액"].sum().sort_values("금액", ascending=False)


def flagged_fund_amount(source: pd.DataFrame, selected: object, flag_name: str) -> float | None:
    """선택한 기준월의 Y/N 입력값을 카드 계산에 그대로 반영한다.

    ``None``은 해당 열 자체가 없는 이전 양식인 경우다. 이 경우에만 월별요약의
    기존 값을 사용해 과거 자료 화면이 갑자기 0원으로 바뀌는 것을 방지한다.
    """
    if source.empty:
        return None
    df = filter_month(source, selected)
    flag_col = find_col(df, [flag_name], required=False)
    amount_col = find_col(df, ["금액", "잔액", "당월금액", "합계", "금액(원)"], required=False)
    if not flag_col or not amount_col:
        return None
    flags = df[flag_col].fillna("").astype(str).str.strip().str.upper()
    return float(df.loc[flags.eq("Y"), amount_col].map(money).sum())


def dashboard_fund_metrics(
    source: pd.DataFrame,
    selected: object,
    net_assets: float,
    summary_restricted: float,
    summary_available: float,
) -> tuple[float, float]:
    """입력 양식의 두 관리 기준을 분리해 KPI에 반영한다.

    - 용도제한자금: ``용도제한여부=Y`` 금액
    - 운영가능자금: 순자금에서 ``운영가능차감여부=Y`` 금액을 뺀 금액

    두 기준은 서로 다를 수 있다. 예를 들어 정기예금은 용도는 제한돼도 실제
    운영에 사용할 수 있으면 각각 Y/N으로 입력할 수 있으므로, 요약시트의
    고정값으로 한쪽을 다른 쪽에 맞춰 계산하면 안 된다.
    """
    restricted = flagged_fund_amount(source, selected, "용도제한여부")
    operational_deduction = flagged_fund_amount(source, selected, "운영가능차감여부")
    shown_restricted = summary_restricted if restricted is None else restricted
    shown_available = summary_available if operational_deduction is None else net_assets - operational_deduction
    return shown_restricted, shown_available


def plot_layout(height: int = 390) -> dict:
    return dict(
        height=height, margin=dict(l=25, r=25, t=35, b=35),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family="Malgun Gothic, sans-serif", size=15, color=INK),
        hoverlabel=dict(font_size=15),
    )


def section(title: str) -> None:
    st.markdown(f'<div class="section">{escape(title)}</div>', unsafe_allow_html=True)


def empty_state(message: str) -> None:
    st.markdown(f'<div class="empty">{escape(message)}</div>', unsafe_allow_html=True)


def build_insights(
    liquid_assets: float,
    liquid_debt: float,
    net_assets: float,
    restricted: float,
    available: float,
    deposits: pd.DataFrame,
    receivables: pd.DataFrame,
) -> list[str]:
    insights: list[str] = []
    debt_ratio = liquid_debt / liquid_assets if liquid_assets else 0
    restricted_ratio = restricted / net_assets if net_assets else 0
    available_ratio = available / net_assets if net_assets else 0

    if debt_ratio <= 0.10:
        debt_view = "유동부채 부담은 낮은 편입니다"
    elif debt_ratio <= 0.25:
        debt_view = "유동부채 부담은 관리 가능한 수준입니다"
    else:
        debt_view = "유동부채 비중이 높아 상환 일정 점검이 필요합니다"
    insights.append(
        f"유동자산 {won(liquid_assets)}에서 유동부채 {won(liquid_debt)}을 제외한 순자금은 "
        f"{won(net_assets)}입니다. 부채비율은 {debt_ratio:.1%}로, {debt_view}."
    )

    if restricted_ratio >= 0.70:
        restriction_view = "자금 대부분의 사용 목적이 제한되어 있어 실제 운영 여력은 넉넉하지 않습니다"
    elif restricted_ratio >= 0.50:
        restriction_view = "순자금의 절반 이상이 지정 목적 자금이므로 일반 운영비 집행 시 구분 관리가 필요합니다"
    else:
        restriction_view = "용도제한 비중이 절반 미만으로 운영 자금의 유연성은 비교적 양호합니다"
    insights.append(
        f"용도제한자금은 {won(restricted)}로 순자금의 {restricted_ratio:.1%}입니다. "
        f"운영가능자금은 {won(available)}({available_ratio:.1%})이며, {restriction_view}."
    )

    if not deposits.empty and deposits["금액"].sum():
        top = deposits.iloc[0]
        concentration = top["금액"] / deposits["금액"].sum()
        note = "예금 분산 여부를 점검할 필요가 있습니다" if concentration >= 0.60 else "예금이 여러 항목에 비교적 분산되어 있습니다"
        insights.append(
            f"보통예금 중 가장 큰 항목은 ‘{top['항목']}’ {won(top['금액'])}이며 전체의 {concentration:.1%}입니다. {note}."
        )

    if not receivables.empty:
        total_receivables = receivables["금액"].sum()
        asset_ratio = total_receivables / liquid_assets if liquid_assets else 0
        top = receivables.iloc[0]
        note = "회수 일정과 장기 미수 여부를 우선 확인해야 합니다" if asset_ratio >= 0.10 else "유동자산 대비 규모는 크지 않지만 정기적인 회수 점검이 필요합니다"
        insights.append(
            f"미수금 합계는 {won(total_receivables)}로 유동자산의 {asset_ratio:.1%}입니다. "
            f"가장 큰 내역은 ‘{top['항목']}’이며, {note}."
        )
    return insights


def money_table(df: pd.DataFrame) -> None:
    shown = df.copy()
    shown["비중"] = shown["금액"] / shown["금액"].sum() if shown["금액"].sum() else 0
    st.dataframe(
        shown,
        hide_index=True,
        use_container_width=True,
        height=min(430, 42 + 36 * len(shown)),
        column_config={
            "항목": st.column_config.TextColumn("항목", width="large"),
            "금액": st.column_config.NumberColumn("금액", format="%,.0f원"),
            "비중": st.column_config.ProgressColumn("비중", min_value=0, max_value=1, format="%.1%%"),
        },
    )


def html_money_table(df: pd.DataFrame, show_share: bool = False) -> str:
    total = float(df["금액"].sum()) if not df.empty else 0
    heads = "<th>세부항목</th><th>금액</th>" + ("<th>비중</th>" if show_share else "")
    rows = []
    for _, row in df.iterrows():
        share = row["금액"] / total if total else 0
        extra = f"<td>{share:.1%}</td>" if show_share else ""
        rows.append(f"<tr><td>{escape(str(row['항목']))}</td><td>{row['금액']:,.0f}</td>{extra}</tr>")
    colspan = 3 if show_share else 2
    cols = ('<colgroup><col class="col-item"><col class="col-money">'
            + ('<col class="col-share">' if show_share else '') + '</colgroup>')
    return (f'<table class="simple-table">{cols}<thead><tr>{heads}</tr></thead><tbody>{"".join(rows)}</tbody>'
            f'<tfoot><tr><td>합계</td><td colspan="{colspan-1}">{total:,.0f}</td></tr></tfoot></table>')


def kpi_card(title: str, value: float, color: str, bg: str) -> str:
    return (f'<div class="kpi" style="--c:{color};--bg:{bg}"><div class="kpi-title">{escape(title)}</div>'
            f'<div class="kpi-main">{value/100_000_000:,.2f}<small>억 원</small></div>'
            f'<div class="kpi-sub">{value:,.0f} 원</div></div>')


upload_password = secret("UPLOAD_PASSWORD")
if "uploader_authorized" not in st.session_state:
    st.session_state.uploader_authorized = False

with st.sidebar:
    st.markdown("## 🌿 자금현황")
    if upload_password and not st.session_state.uploader_authorized:
        st.caption("자료 업로드는 담당자만 가능합니다. 다른 직원은 바로 조회할 수 있습니다.")
        entered_password = st.text_input("업로드 담당자 비밀번호", type="password")
        if st.button("업로드 모드 열기", use_container_width=True):
            if hmac.compare_digest(entered_password, upload_password):
                st.session_state.uploader_authorized = True
                st.rerun()
            else:
                st.error("비밀번호가 맞지 않습니다.")
    elif upload_password and st.session_state.uploader_authorized:
        st.success("업로드 담당자 모드")
        if st.button("업로드 모드 닫기", use_container_width=True):
            st.session_state.uploader_authorized = False
            st.rerun()

    can_upload = st.session_state.uploader_authorized or not upload_password
    uploaded = None
    save_clicked = False
    if can_upload:
        uploaded = st.file_uploader("엑셀 파일 선택", type=["xlsx", "xls"], help="기존 양식 그대로 올려주세요.")
        save_clicked = st.button(
            "월별 자료 저장하기",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        )
        if remote_storage_ready():
            st.caption("새 기준월은 추가되고, 같은 기준월은 최신 파일로 교체됩니다.")
        else:
            st.warning("현재 영구 저장 연결 전입니다. 업로드한 파일은 미리보기만 가능합니다.")
    st.markdown("---")
    st.markdown("**조회 방법**")
    st.markdown("① 기준월 선택  \n② 자금현황·자동분석 확인")

try:
    uploaded_sheets = load_workbook(uploaded.getvalue()) if uploaded else None
    if save_clicked and uploaded_sheets is not None:
        if not remote_storage_ready():
            raise ValueError("영구 저장소가 아직 연결되지 않았습니다.")
        saved_names, saved_months = save_workbook_remote(uploaded_sheets, uploaded.getvalue(), uploaded.name)
        st.sidebar.success(
            f"저장 완료: {', '.join(sorted(saved_months))}\n\n"
            "같은 달 자료가 있으면 최신 내용으로 교체했습니다."
        )
    sheets = load_saved_sheets()
    if sheets:
        data_source = "공유 누적자료"
    elif uploaded_sheets is not None:
        sheets = uploaded_sheets
        data_source = "업로드 미리보기 · 아직 저장되지 않음"
    else:
        st.markdown(
            """
            <div class="hero"><h1>한살림생산자연합회 자금현황</h1>
            <p>월별 누적·공유 대시보드</p></div>
            <div class="upload-welcome"><h2>아직 저장된 기준월이 없습니다</h2>
            <p>업로드 담당자가 왼쪽에서 엑셀을 선택하고 ‘월별 자료 저장하기’를 누르면 대시보드가 열립니다.</p></div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    missing = [name for name in (SHEET_SUMMARY, SHEET_FLOW) if name not in sheets]
    if missing:
        raise ValueError("필수 시트가 없습니다: " + ", ".join(missing))

    summary = sheets[SHEET_SUMMARY]
    month_col = find_col(summary, ["기준월", "월", "년월", "기준년월"])
    months = summary[month_col].dropna().drop_duplicates().tolist()
    if not months:
        raise ValueError("월별요약 시트에 기준월 데이터가 없습니다.")

    default_index = next(
        (index for index in range(len(months) - 1, -1, -1) if has_actual_balance(summary, months[index])),
        len(months) - 1,
    )
    selected = st.sidebar.selectbox("기준월", months, index=default_index, format_func=month_label)
    summary_row = filter_month(summary, selected).iloc[-1]
    liquid_assets = pick_metric(summary_row, ["총유동자산", "유동자산"])
    liquid_debt = pick_metric(summary_row, ["총유동부채", "유동부채"])
    net_assets = pick_metric(summary_row, ["순자금", "순자산", "순유동자산"]) or liquid_assets - liquid_debt
    summary_restricted = pick_metric(summary_row, ["용도제한자금", "제한자금"])
    summary_available = pick_metric(summary_row, ["운영가능자금", "사용가능자금"]) or net_assets - summary_restricted
    source = sheets.get(SHEET_INPUT, pd.DataFrame())
    deposits = display_deposit_labels(
        category_table(source, selected, ["보통예금"]), selected
    )
    limits = restricted_fund_table(source, selected)
    receivables = category_table(source, selected, ["미수금"])
    restricted, available = dashboard_fund_metrics(
        source, selected, net_assets, summary_restricted, summary_available
    )

    st.markdown(f'<div class="hero"><h1>한살림생산자연합회 자금현황 요약</h1>'
                f'<p>{escape(month_label(selected))} 기준 · {escape(data_source)}</p></div>', unsafe_allow_html=True)

    kpis = [
        kpi_card("총 유동자산", liquid_assets, "#1E65C1", "#BFDDF8"), '<div class="op">−</div>',
        kpi_card("유동부채", liquid_debt, "#F04A23", "#F5C6BA"), '<div class="op">=</div>',
        kpi_card("순자금", net_assets, "#7B711A", "#D5EA27"), '<div class="op">−</div>',
        kpi_card("용도제한자금", restricted, "#6E238F", "#DCC1E4"), '<div class="op">·</div>',
        kpi_card("운영가능자금", available, "#328E3C", "#45AD4E")
    ]
    st.markdown('<div class="kpi-grid">'+''.join(kpis)+'</div>', unsafe_allow_html=True)

    # 폭포수보다 보통예금 영역을 넓혀 도넛의 항목명과 비율이 잘리지 않게 한다.
    top_left, top_right = st.columns([.82, 1.18], gap="small")
    with top_left:
        section("자금 흐름 구조")
        # 합계 막대(순자금·운영가능자금)가 증감값으로 중복 계산되지 않도록
        # KPI와 동일한 값과 Waterfall 측정 유형을 명시한다.
        operational_deduction = net_assets - available
        flow_labels = ["총 유동자산", "유동부채 차감", "순자금", "운영가능 차감", "운영가능자금"]
        flow_values = [liquid_assets, -abs(liquid_debt), net_assets, -abs(operational_deduction), available]
        measures = ["absolute", "relative", "total", "relative", "total"]
        fig_flow = go.Figure(go.Waterfall(
            measure=measures, x=flow_labels, y=flow_values,
            text=[won(v) for v in flow_values], textposition="outside",
            textfont=dict(size=15, color=INK),
            increasing={"marker": {"color": GREEN_2}}, decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": BLUE}}, connector={"line": {"color": "#AAB7AE", "width": 2}},
            hovertemplate="<b>%{x}</b><br>%{y:,.0f}원<extra></extra>",
        ))
        fig_flow.update_layout(**plot_layout(350), showlegend=False)
        fig_flow.update_xaxes(tickfont=dict(size=13, color="#000000"), title=None)
        fig_flow.update_yaxes(
            tickformat="~s", gridcolor="#E9EEE9", title=None,
            tickfont=dict(size=12, color="#000000"),
        )
        st.plotly_chart(fig_flow, use_container_width=True, config={"displayModeBar": False})

    with top_right:
        section("보통예금 구성")
        if deposits.empty:
            empty_state("보통예금 상세 항목을 인식하지 못했습니다. 아래 ‘검산·원본’ 화면에서 입력 시트의 열 이름을 확인해 주세요.")
        else:
            # 도넛을 표보다 넓게 배치해 항목명과 비율을 차트 안에서 충분히 보여준다.
            chart_col, table_col = st.columns([1.42, 1], gap="small")
            with chart_col:
                fig = go.Figure(go.Pie(
                    labels=deposits["항목"], values=deposits["금액"], hole=.58,
                    marker=dict(colors=[GREEN, ORANGE, BLUE, "#7EAA8E", "#B5C9B8", "#9A79A7"]),
                    textinfo="label+percent", textposition="auto", textfont=dict(size=15, color="#000000"),
                    hovertemplate="<b>%{label}</b><br>%{value:,.0f}원<br>%{percent}<extra></extra>",
                ))
                fig.add_annotation(text=f"합계<br><b>{won(deposits['금액'].sum())}</b>", showarrow=False, font=dict(size=17, color=INK))
                fig.update_layout(
                    **plot_layout(350),
                    showlegend=False,
                    uniformtext_minsize=12,
                    uniformtext_mode="hide",
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            with table_col:
                st.markdown(f'<div class="table-frame">{html_money_table(deposits, True)}</div>', unsafe_allow_html=True)

    lower1, lower2, lower3 = st.columns([1, 1, 1.22], gap="small")
    with lower1:
        section("미수금 세부내역")
        if receivables.empty:
            empty_state("미수금 상세 항목을 인식하지 못했습니다. 입력 시트에 ‘구분·항목·금액’ 열이 있는지 확인해 주세요.")
        else:
            st.markdown(f'<div class="table-frame compact">{html_money_table(receivables)}</div>', unsafe_allow_html=True)

    with lower2:
        section("용도제한자금 구성")
        if limits.empty:
            empty_state("용도제한자금 항목이 없습니다. 입력 시트의 ‘용도제한여부’ 열에 Y가 표시되어 있는지 확인해 주세요.")
        else:
            ordered = limits.sort_values("금액", ascending=False)
            st.markdown(f'<div class="table-frame compact">{html_money_table(ordered)}</div>', unsafe_allow_html=True)

    with lower3:
        st.markdown('<div class="section" style="background:#C51D22">주요 포인트 · 자동 분석</div>', unsafe_allow_html=True)
        point_list = build_insights(liquid_assets, liquid_debt, net_assets, restricted, available, deposits, receivables)
        for point in point_list:
            st.markdown(f'<div class="point">{escape(point)}</div>', unsafe_allow_html=True)

    with st.expander("업로드 검산 및 원본 데이터 확인"):
        st.success(f"정상 · {len(sheets)}개 시트 · {month_label(selected)}")
        preview_name = st.selectbox("확인할 시트", list(sheets.keys()))
        st.dataframe(sheets[preview_name].head(200), use_container_width=True, height=420)

except Exception as exc:
    st.error(f"자료를 읽거나 저장하는 중 문제가 발생했습니다: {exc}")
    st.info("엑셀 시트명과 첫 번째 헤더 행을 확인해 주세요. 문제가 계속되면 오류 화면을 보내주세요.")
