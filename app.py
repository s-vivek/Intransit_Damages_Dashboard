"""
In-Transit Damage Dashboard — Streamlit + Google Drive
Deploy free at streamlit.io/cloud
Data loads automatically from Google Drive on startup.
"""
import os, io, warnings
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="In-Transit Damage Dashboard",
    page_icon="🚚",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebar"]{background:#1C2833}
[data-testid="stSidebar"] *{color:#fff !important}
.kpi-card{background:#fff;border-radius:8px;padding:14px 16px;
          border-left:4px solid #ccc;box-shadow:0 2px 6px rgba(0,0,0,.08);text-align:center}
</style>
""", unsafe_allow_html=True)

FOLDER_ID = "1gQAobxcPTBDnfmYXsSl9aL_AgrTPBnmo"
COLS = ["Box_ID","source_warehouse_id","destination_warehouse",
        "grn_created_at","prod_cms_vertical","prod_cms_brand",
        "NLC","BU","Week","MLEL Tag","Rate Card Vertical"]
TOP_N = 15

# ── Google Drive helpers ─────────────────────────────────────
def gdrive_list(folder_id):
    API = "https://www.googleapis.com/drive/v3/files"
    files = []
    queue = [folder_id]
    while queue:
        fid = queue.pop()
        params = {
            "q": f"'{fid}' in parents and trashed=false",
            "fields": "files(id,name,mimeType)",
            "pageSize": 1000,
        }
        try:
            r = requests.get(API, params=params, timeout=30)
            items = r.json().get("files", [])
        except Exception:
            items = []
        for item in items:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                queue.append(item["id"])
            elif item["name"].endswith((".csv", ".xlsx")):
                files.append(item)
    return files

def gdrive_download(file_id):
    url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
    session = requests.Session()
    r = session.get(url, stream=True, timeout=60)
    for key, val in r.cookies.items():
        if "download_warning" in key:
            r = session.get(url, params={"confirm": val}, stream=True, timeout=300)
            break
    content = b""
    for chunk in r.iter_content(chunk_size=1024*1024):
        content += chunk
    return content

# ── Load data ────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data():
    status = st.empty()
    status.info("🔄 Connecting to Google Drive...")

    files = gdrive_list(FOLDER_ID)
    if not files:
        st.error("No CSV/XLSX files found. Make sure the Drive folder is shared publicly.")
        st.stop()

    status.info(f"🔄 Found {len(files)} file(s). Downloading... (may take a few minutes on first load)")
    dfs = []
    for i, f in enumerate(files, 1):
        status.info(f"🔄 Downloading {i}/{len(files)}: {f['name']}")
        try:
            content = gdrive_download(f["id"])
            ext = os.path.splitext(f["name"])[1].lower()
            existing_cols = None
            if ext == ".xlsx":
                tmp = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            else:
                try:
                    tmp = pd.read_csv(io.BytesIO(content), encoding="utf-8", low_memory=False)
                except:
                    tmp = pd.read_csv(io.BytesIO(content), encoding="latin1", low_memory=False)

            existing = [c for c in COLS if c in tmp.columns]
            if existing:
                dfs.append(tmp[existing])
        except Exception as e:
            st.warning(f"Skipped {f['name']}: {e}")

    if not dfs:
        st.error("No data loaded. Check file format and Drive permissions.")
        st.stop()

    df = pd.concat(dfs, ignore_index=True)
    df = df.loc[:, ~df.columns.duplicated()]

    if "Rate Card Vertical" not in df.columns:
        df["Rate Card Vertical"] = "N/A"

    df["NLC"] = pd.to_numeric(df["NLC"], errors="coerce").fillna(0)
    df["grn_created_at"] = df["grn_created_at"].astype(str).str.strip()
    df["grn_created_at"] = df["grn_created_at"].str.replace(
        r'(\d{4}-\d{2}-\d{2}) (\d{2})\.(\d{2})\.(\d{2})',
        r'\1 \2:\3:\4', regex=True)
    df["grn_created_at"] = pd.to_datetime(df["grn_created_at"], errors="coerce")
    df["Date"]       = df["grn_created_at"].dt.strftime("%Y-%m-%d")
    df["Month"]      = df["grn_created_at"].dt.strftime("%Y-%m")
    df["MonthLabel"] = df["grn_created_at"].dt.strftime("%b %Y")
    df["YearWeek"]   = df["grn_created_at"].dt.strftime("%Y-W%V")

    for c in ["source_warehouse_id","destination_warehouse","prod_cms_vertical",
              "prod_cms_brand","BU","MLEL Tag","Rate Card Vertical"]:
        if c in df.columns:
            df[c] = df[c].fillna("Unknown").astype(str).str.strip()

    status.empty()
    return df, len(files)

DF, n_files = load_data()

# ── Sidebar filters ──────────────────────────────────────────
st.sidebar.title("🚚 In-Transit Damage")
st.sidebar.markdown(f"**{n_files} file(s) · {len(DF):,} records**")
st.sidebar.markdown("---")

month_opts   = sorted(DF["Month"].dropna().unique().tolist())
month_labels = {m: DF[DF["Month"]==m]["MonthLabel"].iloc[0] for m in month_opts}
sel_months   = st.sidebar.multiselect("Month", options=month_opts,
                                      format_func=lambda x: month_labels.get(x, x))

week_opts  = sorted(DF["YearWeek"].dropna().unique().tolist())
sel_weeks  = st.sidebar.multiselect("Week", week_opts)

def ms(label, col):
    opts = sorted(DF[col].dropna().unique().tolist())
    return st.sidebar.multiselect(label, opts)

sel_src    = ms("Source WH",         "source_warehouse_id")
sel_dst    = ms("Dest WH",           "destination_warehouse")
sel_vert   = ms("Vertical",          "prod_cms_vertical")
sel_rcvert = ms("Rate Card Vertical","Rate Card Vertical")
sel_brand  = ms("Brand",             "prod_cms_brand")
sel_bu     = ms("BU",                "BU")
sel_mlel   = ms("MLEL Tag",          "MLEL Tag")

st.sidebar.markdown("---")
do_reset = st.sidebar.button("✕ Reset All", use_container_width=True)
if do_reset:
    st.rerun()

# ── Filter ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def filter_df(months, weeks, srcs, dsts, verts, rcverts, brands, bus, mlels):
    df = DF.copy()
    if months:  df = df[df["Month"].isin(months)]
    if weeks:   df = df[df["YearWeek"].isin(weeks)]
    if srcs:    df = df[df["source_warehouse_id"].isin(srcs)]
    if dsts:    df = df[df["destination_warehouse"].isin(dsts)]
    if verts:   df = df[df["prod_cms_vertical"].isin(verts)]
    if rcverts: df = df[df["Rate Card Vertical"].isin(rcverts)]
    if brands:  df = df[df["prod_cms_brand"].isin(brands)]
    if bus:     df = df[df["BU"].isin(bus)]
    if mlels:   df = df[df["MLEL Tag"].isin(mlels)]
    return df

df = filter_df(
    tuple(sel_months), tuple(sel_weeks), tuple(sel_src),
    tuple(sel_dst), tuple(sel_vert), tuple(sel_rcvert),
    tuple(sel_brand), tuple(sel_bu), tuple(sel_mlel)
)

# ── Header ───────────────────────────────────────────────────
st.title("🚚 In-Transit Damage Dashboard")
st.caption(f"{n_files} file(s) · {len(df):,} records shown")

# ── KPIs ─────────────────────────────────────────────────────
total_boxes = int(df["Box_ID"].nunique()) if "Box_ID" in df.columns else 0
total_nlc   = float(df["NLC"].sum())
avg_nlc     = round(total_nlc / total_boxes, 2) if total_boxes else 0

k1,k2,k3,k4,k5 = st.columns(5)
def kpi(col, label, value, color):
    col.markdown(f"""
    <div class="kpi-card" style="border-left-color:{color}">
      <div style="font-size:10px;color:#95A5A6;text-transform:uppercase">{label}</div>
      <div style="font-size:18px;font-weight:700;color:{color}">{value}</div>
    </div>""", unsafe_allow_html=True)

kpi(k1, "Total Boxes",   f"{total_boxes:,}",                              "#1C2833")
kpi(k2, "Total NLC",     f"Rs.{total_nlc:,.0f}",                         "#E74C3C")
kpi(k3, "Avg NLC/Box",   f"Rs.{avg_nlc:,.2f}",                           "#E67E22")
kpi(k4, "Source WHs",    f"{df['source_warehouse_id'].nunique():,}",      "#2980B9")
kpi(k5, "Dest WHs",      f"{df['destination_warehouse'].nunique():,}",    "#1ABC9C")

st.markdown("<br>", unsafe_allow_html=True)

# ── Chart helpers ─────────────────────────────────────────────
LAYOUT = dict(plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
              font=dict(family="Arial", size=11), showlegend=False)

def hbar_nlc(col, title, color, n=TOP_N):
    t = df.groupby(col)["NLC"].sum().nlargest(n).reset_index().sort_values("NLC")
    if t.empty: return go.Figure()
    fig = px.bar(t, x="NLC", y=col, orientation="h", title=title,
                 text=t["NLC"].apply(lambda v: f"Rs.{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(**LAYOUT, margin=dict(l=10,r=80,t=40,b=10),
                      yaxis_title="", xaxis_title="NLC (Rs.)")
    return fig

def vbar_nlc(grp_col, sort_col, title, color):
    t = df.groupby([sort_col, grp_col])["NLC"].sum().reset_index().sort_values(sort_col)
    if t.empty: return go.Figure()
    fig = px.bar(t, x=grp_col, y="NLC", title=title,
                 text=t["NLC"].apply(lambda v: f"Rs.{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="NLC (Rs.)",
                      xaxis_tickangle=-45, margin=dict(t=40,b=80))
    return fig

def pie_chart(col, title, n=15):
    t = df.groupby(col)["NLC"].sum().nlargest(n).reset_index()
    if t.empty: return go.Figure()
    fig = px.pie(t, names=col, values="NLC", title=title, hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(margin=dict(l=10,r=10,t=40,b=10), paper_bgcolor="#fff")
    return fig

# ── Trends ────────────────────────────────────────────────────
st.subheader("📈 Trends")

tm = df.groupby(["Month","MonthLabel"])["NLC"].sum().reset_index().sort_values("Month")
fig = px.bar(tm, x="MonthLabel", y="NLC", title="Monthly NLC Trend (Rs.)",
             text=tm["NLC"].apply(lambda v: f"Rs.{v:,.0f}"),
             color_discrete_sequence=["#1ABC9C"])
fig.update_traces(textposition="outside")
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="NLC (Rs.)", margin=dict(t=40,b=40))
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
tw = df.groupby("YearWeek")["NLC"].sum().reset_index().sort_values("YearWeek")
fig = px.bar(tw, x="YearWeek", y="NLC", title="Week-wise NLC (Rs.)",
             text=tw["NLC"].apply(lambda v: f"Rs.{v:,.0f}"),
             color_discrete_sequence=["#3498DB"])
fig.update_traces(textposition="outside")
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="NLC (Rs.)",
                  xaxis_tickangle=-45, margin=dict(t=40,b=80))
c1.plotly_chart(fig, use_container_width=True)

td = df.groupby("Date")["NLC"].sum().reset_index().sort_values("Date")
fig = px.bar(td, x="Date", y="NLC", title="Day-wise NLC (Rs.)",
             color_discrete_sequence=["#E74C3C"])
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="NLC (Rs.)",
                  xaxis_tickangle=-45, margin=dict(t=40,b=80))
c2.plotly_chart(fig, use_container_width=True)

# ── Warehouse View ────────────────────────────────────────────
st.subheader("🏭 Warehouse View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_nlc("source_warehouse_id",  "Source WH by NLC", "#E74C3C"), use_container_width=True)
c2.plotly_chart(hbar_nlc("destination_warehouse","Dest WH by NLC",   "#E67E22"), use_container_width=True)

# ── Product View ───────────────────────────────────────────────
st.subheader("📦 Product View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_nlc("prod_cms_vertical", "Product Vertical by NLC",    "#3498DB"), use_container_width=True)
c2.plotly_chart(hbar_nlc("Rate Card Vertical","Rate Card Vertical by NLC",  "#F39C12"), use_container_width=True)

c1, c2 = st.columns(2)
c1.plotly_chart(hbar_nlc("prod_cms_brand", "Brand by NLC", "#8E44AD"), use_container_width=True)
c2.plotly_chart(hbar_nlc("BU",             "BU by NLC",    "#1ABC9C"), use_container_width=True)

# ── MLEL Split ────────────────────────────────────────────────
st.subheader("🏷️ MLEL Split")
st.plotly_chart(pie_chart("MLEL Tag", "MLEL Tag Split", 50), use_container_width=True)

st.caption(f"In-Transit Damage Dashboard · Streamlit Cloud · {len(df):,} records")
