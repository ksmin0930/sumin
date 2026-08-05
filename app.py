from __future__ import annotations

import io
import re
from html import escape
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


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
DEFAULT_SPREADSHEET_ID = "1fr-An3ezXl9SyO72WfDKKlM4yPN6XTE2_pckjzp2zOM"
SYNC_SHEETS = (SHEET_INPUT, SHEET_SUMMARY, SHEET_FLOW)

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
    .simple-table{width:100%;border-collapse:collapse;font-size:.88rem}
    .simple-table th{background:#E7EEF9;padding:.38rem;text-align:right}.simple-table th:first-child{text-align:left}
    .simple-table td{padding:.32rem .38rem;border-bottom:1px solid #ECEDEF;text-align:right}.simple-table td:first-child{text-align:left}
    .simple-table tfoot td{font-weight:900;border-top:2px solid #C9CDD3;border-bottom:0}
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
    return df.loc[:, ~df.columns.str.startswith("Unnamed")]


def google_configured() -> bool:
    try:
        return "gcp_service_account" in st.secrets
    except Exception:
        return False


def google_client():
    if not google_configured():
        raise ValueError("Google Sheets 쓰기 설정이 없습니다. README의 ‘Google Sheets 연결’ 단계를 먼저 진행해 주세요.")
    if gspread is None or Credentials is None:
        raise ValueError("Google Sheets 연결 패키지가 설치되지 않았습니다. requirements.txt를 다시 설치해 주세요.")
    info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(credentials)


def spreadsheet_id() -> str:
    return str(st.secrets.get("spreadsheet_id", DEFAULT_SPREADSHEET_ID))


def records_to_frame(values: list[list[str]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    width = max(len(row) for row in values)
    rows = [row + [""] * (width - len(row)) for row in values]
    headers = [str(v).strip() or f"열_{i+1}" for i, v in enumerate(rows[0])]
    return clean_frame(pd.DataFrame(rows[1:], columns=headers))


@st.cache_data(ttl=60, show_spinner=False)
def load_google_sheets(sheet_id: str) -> dict[str, pd.DataFrame]:
    book = google_client().open_by_key(sheet_id)
    result: dict[str, pd.DataFrame] = {}
    for worksheet in book.worksheets():
        values = worksheet.get_all_values()
        if values:
            result[worksheet.title.strip()] = records_to_frame(values)
    return result


def month_keys(df: pd.DataFrame) -> set[str]:
    col = find_col(df, ["기준월", "월", "년월", "기준년월"], required=False)
    if not col:
        return set()
    return {month_label(value) for value in df[col].dropna() if str(value).strip()}


def merge_by_month(existing: pd.DataFrame, incoming: pd.DataFrame, uploaded_months: set[str]) -> pd.DataFrame:
    incoming = clean_frame(incoming)
    if existing.empty:
        return incoming
    old_month_col = find_col(existing, ["기준월", "월", "년월", "기준년월"], required=False)
    new_month_col = find_col(incoming, ["기준월", "월", "년월", "기준년월"], required=False)
    if not old_month_col or not new_month_col:
        return incoming
    keep = existing[~existing[old_month_col].map(month_label).isin(uploaded_months)].copy()
    columns = list(dict.fromkeys([*keep.columns, *incoming.columns]))
    return pd.concat([keep.reindex(columns=columns), incoming.reindex(columns=columns)], ignore_index=True)


def sheet_values(df: pd.DataFrame) -> list[list[object]]:
    safe = df.copy().fillna("")
    for column in safe.columns:
        safe[column] = safe[column].map(
            lambda value: value.isoformat() if isinstance(value, (pd.Timestamp,)) else value
        )
    return [safe.columns.tolist(), *safe.astype(object).values.tolist()]


def save_workbook_to_google(incoming: dict[str, pd.DataFrame]) -> tuple[list[str], set[str]]:
    summary = incoming[SHEET_SUMMARY]
    uploaded_months = month_keys(summary)
    if not uploaded_months:
        raise ValueError("업로드 파일에서 저장할 기준월을 찾지 못했습니다.")
    book = google_client().open_by_key(spreadsheet_id())
    saved: list[str] = []
    for name in SYNC_SHEETS:
        if name not in incoming:
            if name in (SHEET_SUMMARY, SHEET_FLOW):
                raise ValueError(f"필수 시트가 없습니다: {name}")
            continue
        try:
            worksheet = book.worksheet(name)
            existing = records_to_frame(worksheet.get_all_values())
        except gspread.WorksheetNotFound:
            worksheet = book.add_worksheet(title=name, rows=100, cols=max(10, len(incoming[name].columns)))
            existing = pd.DataFrame()
        merged = merge_by_month(existing, incoming[name], uploaded_months)
        values = sheet_values(merged)
        worksheet.clear()
        worksheet.resize(rows=max(100, len(values) + 20), cols=max(10, len(values[0]) + 2))
        worksheet.update(values=values, range_name="A1", value_input_option="USER_ENTERED")
        saved.append(name)
    load_google_sheets.clear()
    return saved, uploaded_months


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


def category_table(source: pd.DataFrame, selected: object, keywords: list[str]) -> pd.DataFrame:
    if source.empty:
        return pd.DataFrame(columns=["항목", "금액"])
    df = filter_month(source, selected)
    kind_col = find_col(df, ["구분", "대분류", "자금구분", "분류", "유동자산구분"], required=False)
    item_col = find_col(df, ["항목", "세부항목", "계정명", "내역", "예금명", "세부내역"], required=False)
    amount_col = find_col(df, ["금액", "잔액", "당월금액", "합계", "금액(원)"], required=False)
    if not item_col or not amount_col:
        return pd.DataFrame(columns=["항목", "금액"])
    if kind_col:
        mask = df[kind_col].astype(str).map(norm).apply(lambda x: any(norm(k) in x for k in keywords))
        df = df[mask]
    result = pd.DataFrame({"항목": df[item_col].fillna("미분류").astype(str), "금액": df[amount_col].map(money)})
    result = result[result["금액"] != 0]
    return result.groupby("항목", as_index=False)["금액"].sum().sort_values("금액", ascending=False)


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
    return (f'<table class="simple-table"><thead><tr>{heads}</tr></thead><tbody>{"".join(rows)}</tbody>'
            f'<tfoot><tr><td>합계</td><td colspan="{colspan-1}">{total:,.0f}</td></tr></tfoot></table>')


def kpi_card(title: str, value: float, color: str, bg: str) -> str:
    return (f'<div class="kpi" style="--c:{color};--bg:{bg}"><div class="kpi-title">{escape(title)}</div>'
            f'<div class="kpi-main">{value/100_000_000:,.2f}<small>억 원</small></div>'
            f'<div class="kpi-sub">{value:,.0f} 원</div></div>')


with st.sidebar:
    st.markdown("## 🌿 자금현황")
    st.caption("Google Sheets에 월별 자료를 누적하고 언제든 과거 자료를 조회합니다.")
    uploaded = st.file_uploader("엑셀 파일 선택", type=["xlsx", "xls"], help="기존 양식 그대로 올려주세요.")
    save_clicked = st.button(
        "Google Sheets에 저장",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or not google_configured(),
    )
    if google_configured():
        st.success("Google Sheets 연결됨")
    else:
        st.warning("Google Sheets 쓰기 설정 필요")
    st.markdown("---")
    st.markdown("**사용 방법**")
    st.markdown("① 엑셀 업로드  \n② 저장 버튼 클릭  \n③ 기준월 선택")
    st.caption("같은 기준월을 다시 저장하면 해당 월 자료만 최신 내용으로 교체됩니다.")

try:
    uploaded_sheets = load_workbook(uploaded.getvalue()) if uploaded else None
    if save_clicked and uploaded_sheets is not None:
        saved_names, saved_months = save_workbook_to_google(uploaded_sheets)
        st.sidebar.success(
            f"저장 완료: {', '.join(sorted(saved_months))}\n\n"
            f"{len(saved_names)}개 시트가 갱신됐습니다."
        )

    if google_configured():
        with st.spinner("Google Sheets 누적 자료를 불러오는 중입니다..."):
            sheets = load_google_sheets(spreadsheet_id())
        data_source = "Google Sheets 누적 자료"
    elif uploaded_sheets is not None:
        sheets = uploaded_sheets
        data_source = "업로드 미리보기 · 아직 저장되지 않음"
    else:
        st.markdown(
            """
            <div class="hero"><h1>한살림생산자연합회 자금현황</h1>
            <p>Google Sheets 누적 저장형 대시보드</p></div>
            <div class="upload-welcome"><h2>Google Sheets 연결 설정이 필요합니다</h2>
            <p>README의 연결 단계를 한 번만 완료하면, 이후 업로드 자료가 월별로 계속 누적됩니다.</p></div>
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

    selected = st.sidebar.selectbox("기준월", months, index=len(months) - 1, format_func=month_label)
    summary_row = filter_month(summary, selected).iloc[-1]
    liquid_assets = pick_metric(summary_row, ["총유동자산", "유동자산"])
    liquid_debt = pick_metric(summary_row, ["총유동부채", "유동부채"])
    net_assets = pick_metric(summary_row, ["순자금", "순자산", "순유동자산"]) or liquid_assets - liquid_debt
    restricted = pick_metric(summary_row, ["용도제한자금", "제한자금"])
    available = pick_metric(summary_row, ["운영가능자금", "사용가능자금"]) or net_assets - restricted
    debt_ratio = liquid_debt / liquid_assets if liquid_assets else 0
    available_ratio = available / net_assets if net_assets else 0
    source = sheets.get(SHEET_INPUT, pd.DataFrame())
    deposits = category_table(source, selected, ["보통예금", "예금"])
    limits = category_table(source, selected, ["용도제한", "제한자금"])
    receivables = category_table(source, selected, ["미수금"])

    st.markdown(f'<div class="hero"><h1>한살림생산자연합회 자금현황 요약</h1>'
                f'<p>{escape(month_label(selected))} 기준 · {escape(data_source)}</p></div>', unsafe_allow_html=True)

    kpis = [
        kpi_card("총 유동자산", liquid_assets, "#1E65C1", "#BFDDF8"), '<div class="op">−</div>',
        kpi_card("유동부채", liquid_debt, "#F04A23", "#F5C6BA"), '<div class="op">=</div>',
        kpi_card("순자금", net_assets, "#7B711A", "#D5EA27"), '<div class="op">−</div>',
        kpi_card("용도제한자금", restricted, "#6E238F", "#DCC1E4"), '<div class="op">=</div>',
        kpi_card("운영가능자금", available, "#328E3C", "#45AD4E")
    ]
    st.markdown('<div class="kpi-grid">'+''.join(kpis)+'</div>', unsafe_allow_html=True)

    top_left, top_right = st.columns([1, 1], gap="small")
    with top_left:
        section("자금 흐름 구조")
        flow = filter_month(sheets[SHEET_FLOW], selected)
        flow_label = find_col(flow, ["항목", "구분", "단계", "자금흐름"])
        flow_amount = find_col(flow, ["금액", "값", "금액원", "잔액"])
        flow = flow[[flow_label, flow_amount]].dropna(subset=[flow_label]).copy()
        flow[flow_amount] = flow[flow_amount].map(money)
        measures = ["relative"] * len(flow)
        if measures:
            measures[0], measures[-1] = "absolute", "total"
        fig_flow = go.Figure(go.Waterfall(
            measure=measures, x=flow[flow_label], y=flow[flow_amount],
            text=[won(v) for v in flow[flow_amount]], textposition="outside",
            textfont=dict(size=15, color=INK),
            increasing={"marker": {"color": GREEN_2}}, decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": BLUE}}, connector={"line": {"color": "#AAB7AE", "width": 2}},
            hovertemplate="<b>%{x}</b><br>%{y:,.0f}원<extra></extra>",
        ))
        fig_flow.update_layout(**plot_layout(330), showlegend=False)
        fig_flow.update_yaxes(tickformat="~s", gridcolor="#E9EEE9", title=None)
        st.plotly_chart(fig_flow, use_container_width=True, config={"displayModeBar": False})

    with top_right:
        section("보통예금 구성")
        if deposits.empty:
            empty_state("보통예금 상세 항목을 인식하지 못했습니다. 아래 ‘검산·원본’ 화면에서 입력 시트의 열 이름을 확인해 주세요.")
        else:
            chart_col, table_col = st.columns([.95, 1.2], gap="small")
            with chart_col:
                fig = go.Figure(go.Pie(
                    labels=deposits["항목"], values=deposits["금액"], hole=.58,
                    marker=dict(colors=[GREEN, ORANGE, BLUE, "#7EAA8E", "#B5C9B8", "#9A79A7"]),
                    textinfo="label+percent", textfont=dict(size=15),
                    hovertemplate="<b>%{label}</b><br>%{value:,.0f}원<br>%{percent}<extra></extra>",
                ))
                fig.add_annotation(text=f"합계<br><b>{won(deposits['금액'].sum())}</b>", showarrow=False, font=dict(size=17, color=INK))
                fig.update_layout(**plot_layout(330), showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            with table_col:
                st.markdown(html_money_table(deposits, True), unsafe_allow_html=True)

    lower1, lower2, lower3 = st.columns([1, 1, 1], gap="small")
    with lower1:
        section("미수금 세부내역")
        if receivables.empty:
            empty_state("미수금 상세 항목을 인식하지 못했습니다. 입력 시트에 ‘구분·항목·금액’ 열이 있는지 확인해 주세요.")
        else:
            st.markdown(html_money_table(receivables), unsafe_allow_html=True)

    with lower2:
        section("용도제한자금 구성")
        if limits.empty:
            empty_state("용도제한자금 상세 항목을 인식하지 못했습니다. 입력 시트의 분류명이 ‘용도제한자금’인지 확인해 주세요.")
        else:
            ordered = limits.sort_values("금액", ascending=False)
            st.markdown(html_money_table(ordered), unsafe_allow_html=True)

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
    st.info("Google Sheets 공유 권한, 서비스 계정 설정, 엑셀 시트명과 첫 번째 헤더 행을 확인해 주세요.")
