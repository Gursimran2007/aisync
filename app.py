"""AISync — AI-Based Spare Inventory Optimization for Haldia Petrochemicals.

An enterprise console that turns a plant's spare-parts master (SAP-style) into
working-capital decisions. Every number shown is COMPUTED from the plant's own
consumption/stock data — never guessed — so the grounding guarantee holds.

Eight-page layout (sidebar nav):
  1. Executive Dashboard  — ₹Cr capital, release opportunity, criticality mix
  2. Obsolete Detection   — dead/obsolete stock (no movement >5 yrs) + release value
  3. Consumption Forecast — the from-scratch neural forecaster's read per spare
  4. Criticality Optimizer— reorder by shutdown risk; insurance spares; budget plan
  5. Predictive Maint.    — accelerating consumption = an equipment failure signal
  6. Spare Master & Data   — record issues/receipts, set stock, SAP export auto-map
  7. Ask AISync           — grounded Q&A over the plant's real numbers
  8. Implementation Roadmap— the 5-phase SAP-integrated rollout
"""
import html
import uuid

import pandas as pd
import streamlit as st

from core import db
from core import auth
from core.adapters import TabularAdapter, ManualAdapter
from core.seed import seed_db, write_messy_excel
from core.engine import build_report, CRITICALITY_SERVICE
from core import spares

st.set_page_config(page_title="AISync — Spare Inventory Optimization",
                   page_icon="◆", layout="wide")


@st.cache_resource
def _init_auth():
    """Create the auth tables once per server process (not per rerun)."""
    auth.init()
    return True


_init_auth()

# In-brand mark: a hexagonal node cluster (spare/molecule motif).
LOGO_MARK = (
    "<svg width='22' height='22' viewBox='0 0 24 24' fill='none' "
    "xmlns='http://www.w3.org/2000/svg'>"
    "<path d='M12 2.4 20.5 7v10L12 21.6 3.5 17V7L12 2.4Z' "
    "stroke='#fff' stroke-opacity='.9' stroke-width='1.4' fill='none'/>"
    "<circle cx='12' cy='12' r='2.3' fill='#fff'/>"
    "<circle cx='12' cy='6.2' r='1.3' fill='#fff' fill-opacity='.85'/>"
    "<circle cx='17' cy='15' r='1.3' fill='#fff' fill-opacity='.85'/>"
    "<circle cx='7' cy='15' r='1.3' fill='#fff' fill-opacity='.85'/>"
    "</svg>"
)


def inject_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&display=swap');
      :root{
        --bg:#F4F6FA; --surface:#FFFFFF; --border:#E1E7F0; --border-2:#EDF1F7;
        --text:#141B26; --muted:#5B6879; --accent:#1F4E79; --accent-2:#2C6699;
        --accent-soft:#E7EFF7; --teal:#0E7C86;
        --radius:12px; --radius-sm:9px;
        --shadow-sm:0 1px 2px rgba(20,27,38,.06), 0 1px 3px rgba(20,27,38,.05);
        --shadow-md:0 4px 14px rgba(20,27,38,.08), 0 1px 3px rgba(20,27,38,.05);
        --ease:cubic-bezier(.4,0,.2,1);
      }
      html, body, [class*="css"] { font-family:'Inter',sans-serif; color:var(--text);
        -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
      html{ scroll-behavior:smooth; }
      .stApp { background:
        radial-gradient(1200px 600px at 100% -10%, #E8EFF8 0%, transparent 55%),
        var(--bg); }
      header[data-testid="stHeader"]{ background:transparent; }
      [data-testid="stToolbar"]{ display:none; }
      @keyframes ssRise{ from{opacity:0; transform:translateY(6px);} to{opacity:1; transform:none;} }
      .main .block-container{ animation:ssRise .28s var(--ease) both; }
      [data-testid="stSidebar"][aria-expanded="false"]{
        transform:none !important;
        width:46px !important; min-width:46px !important;
        overflow:hidden !important;
        background:var(--surface); border-right:1px solid var(--border);
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"]{ display:none !important; }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"]{
        width:46px !important; padding:8px 0 !important;
        justify-content:center !important; overflow:visible !important;
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"]{
        transform:none !important; z-index:1000;
        visibility:visible !important; opacity:1 !important;
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] button{
        visibility:visible !important; opacity:1 !important;
        color:var(--accent); background:var(--surface);
        border:1px solid var(--border); border-radius:8px;
        box-shadow:0 1px 3px rgba(0,0,0,.08);
      }
      .block-container { padding-top:2.4rem; max-width:1240px; }
      h1,h2,h3,h4 { letter-spacing:-.015em; font-weight:600; }

      .appbar{
        display:flex; align-items:center; gap:14px;
        padding:0 0 16px; margin-bottom:18px; border-bottom:1px solid var(--border);
      }
      .appbar .logo{
        width:42px; height:42px; border-radius:12px; flex:0 0 42px;
        background:linear-gradient(145deg, #2C6699, var(--accent) 55%, #163A5A);
        display:flex; align-items:center; justify-content:center;
        box-shadow:0 4px 12px rgba(31,78,121,.32),
                   inset 0 1px 0 rgba(255,255,255,.22),
                   inset 0 -2px 6px rgba(0,0,0,.12);
        transition:transform .2s var(--ease), box-shadow .2s var(--ease);
      }
      .appbar .logo:hover{ transform:translateY(-1px) rotate(-2deg); }
      .appbar .logo svg{ display:block; }
      .appbar .brand-name{ font-size:1.2rem; font-weight:680; line-height:1.1; }
      .appbar .brand-sub{ font-size:.86rem; color:var(--muted); margin-top:2px; }

      [data-testid="stMetric"]{
        background:var(--surface); border:1px solid var(--border);
        border-radius:var(--radius); padding:16px 18px;
        box-shadow:var(--shadow-sm); position:relative; overflow:hidden;
        transition:transform .18s var(--ease), box-shadow .18s var(--ease);
      }
      [data-testid="stMetric"]::before{
        content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
        background:linear-gradient(var(--accent-2), var(--accent)); opacity:.9;
      }
      [data-testid="stMetric"]:hover{ transform:translateY(-2px); box-shadow:var(--shadow-md); }
      [data-testid="stMetricLabel"] p{
        font-size:.72rem !important; font-weight:600; letter-spacing:.04em;
        text-transform:uppercase; color:var(--muted);
      }
      [data-testid="stMetricValue"]{ font-weight:680; font-size:1.6rem; }

      .stButton>button, .stDownloadButton>button, .stLinkButton>a,
      [data-testid="stFormSubmitButton"]>button{
        border-radius:var(--radius-sm); font-weight:550; font-size:.92rem;
        border:1px solid var(--border); background:var(--surface); color:var(--text);
        box-shadow:var(--shadow-sm);
        transition:background .16s var(--ease), border-color .16s var(--ease),
                   transform .16s var(--ease), box-shadow .16s var(--ease);
      }
      .stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover{
        border-color:#C3D2E4; background:#F2F6FB;
        transform:translateY(-1px); box-shadow:var(--shadow-md);
      }
      .stButton>button:active, [data-testid="stFormSubmitButton"]>button:active{
        transform:translateY(0); box-shadow:var(--shadow-sm);
      }
      .stButton>button[kind="primary"], .stLinkButton>a[kind="primary"],
      [data-testid="stFormSubmitButton"]>button[kind="primary"]{
        background:var(--accent); border:1px solid var(--accent); color:#fff;
      }
      .stButton>button[kind="primary"]:hover,
      [data-testid="stFormSubmitButton"]>button[kind="primary"]:hover{
        background:var(--accent-2); border-color:var(--accent-2);
      }

      [data-testid="stSidebar"]{ background:var(--surface); border-right:1px solid var(--border); }
      [data-testid="stSidebar"] .nav-head{
        font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
        color:var(--muted); padding:2px 6px 6px;
      }
      [data-testid="stSidebar"] [role="radiogroup"]{ gap:1px; }
      [data-testid="stSidebar"] [role="radiogroup"] label{
        display:flex; width:100%; border-radius:6px; padding:9px 12px; margin:0;
        cursor:pointer; font-weight:500; font-size:.92rem; color:var(--text);
        border-left:3px solid transparent; transition:background .12s, color .12s;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:hover{ background:#F0F4F9; }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
        background:var(--accent-soft); color:var(--accent);
        border-left:3px solid var(--accent); font-weight:600;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{ color:var(--accent); font-weight:600; }
      [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child{ display:none; }

      [data-testid="stExpander"]{
        border:1px solid var(--border); border-radius:var(--radius);
        box-shadow:var(--shadow-sm); overflow:hidden; background:var(--surface);
        transition:box-shadow .18s var(--ease);
      }
      [data-testid="stExpander"]:hover{ box-shadow:var(--shadow-md); }
      [data-testid="stExpander"] summary:hover{ color:var(--accent); }
      [data-testid="stDataFrame"], [data-testid="stTable"]{
        border-radius:var(--radius-sm); overflow:hidden; border:1px solid var(--border);
        box-shadow:var(--shadow-sm);
      }
      [data-testid="stSidebar"] .stButton>button{ font-size:.86rem; }
      hr{ margin:1rem 0; border-color:var(--border-2); }

      /* domain callout cards */
      .card{ background:var(--surface); border:1px solid var(--border);
        border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow-sm);
        margin-bottom:10px; }
      .card h4{ margin:.1rem 0 .3rem; }
      .pill{ display:inline-block; padding:2px 9px; border-radius:20px;
        font-size:.72rem; font-weight:600; letter-spacing:.02em; }
      .pill-crit{ background:#FBE7E1; color:#B4543A; }
      .pill-ess{ background:#FDF3DF; color:#9A7420; }
      .pill-non{ background:#E7EFF7; color:#2C6699; }

      [data-testid="stChatMessage"]{
        background:var(--surface); border:1px solid var(--border);
        border-radius:14px; padding:2px 6px; box-shadow:var(--shadow-sm);
        animation:ssRise .24s var(--ease) both;
      }
      [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
        background:var(--accent-soft); border-color:#CFDEEC;
      }
      [data-testid="stChatInput"] textarea{ border-radius:12px; }
      [data-testid="stTextInput"] input:focus,
      [data-testid="stNumberInput"] input:focus,
      [data-baseweb="select"] > div:focus-within{
        border-color:var(--accent) !important;
        box-shadow:0 0 0 2px var(--accent-soft) !important;
      }
    </style>
    """, unsafe_allow_html=True)


inject_css()

TAGLINE = "AI-based spare inventory optimization — release working capital without risking a shutdown."

CANON_FIELDS = ["sku", "name", "date", "qty", "stock", "unit_cost",
                "lead_time_days", "reliability"]

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
DOT = {"high": "#B4543A", "medium": "#C8A04B", "low": "#5C7A5E"}
CRIT_PILL = {"critical": "pill-crit", "essential": "pill-ess",
             "non-critical": "pill-non"}


def _dot(color):
    return f"<span style='color:{color};font-size:1.05em'>&#9679;</span>"


def _crit_pill(crit):
    return f"<span class='pill {CRIT_PILL.get(crit,'pill-non')}'>{_esc(crit)}</span>"


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _sku_from_name(name, taken):
    import re
    base = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().upper()).strip("-")
    base = base[:14] or "SPARE"
    sku, i = base, 2
    while sku in taken:
        sku = f"{base}-{i}"; i += 1
    return sku


# ============================================================ AUTH GATE
def _activate_plant(user):
    st.session_state["uid"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["plant_name"] = user.get("shop_name") or user["username"]
    db.set_shop(user["id"])
    db.init_db()


def _render_login():
    st.markdown(
        f"<div class='appbar'><div class='logo'>{LOGO_MARK}</div>"
        "<div><div class='brand-name'>AISync</div>"
        "<div class='brand-sub'>Sign in to your plant workspace</div></div></div>",
        unsafe_allow_html=True)
    st.caption("AI-Based Spare Inventory Optimization Model — Haldia Petrochemicals")
    tab_login, tab_signup = st.tabs(["Log in", "Create plant workspace"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", use_container_width=True)
        if ok:
            try:
                user = auth.login(u, p)
            except auth.AuthError as e:
                st.error(str(e))
            else:
                token = auth.create_session(user["id"])
                st.query_params["s"] = token
                db.log_event("login", uid=user["id"], visitor=_visitor_id())
                _activate_plant(user)
                st.rerun()

    with tab_signup:
        with st.form("signup_form"):
            plant = st.text_input("Plant / site name",
                                  placeholder="e.g. Haldia Petrochemicals — Naphtha Cracker")
            u2 = st.text_input("Choose a username")
            p2 = st.text_input("Choose a password (6+ characters)", type="password")
            p3 = st.text_input("Repeat password", type="password")
            ok2 = st.form_submit_button("Create workspace", use_container_width=True)
        if ok2:
            if p2 != p3:
                st.error("The two passwords don't match.")
            else:
                try:
                    uid = auth.signup(u2, p2, plant)
                except auth.AuthError as e:
                    st.error(str(e))
                else:
                    user = {"id": uid, "username": auth._norm(u2),
                            "shop_name": plant.strip()}
                    token = auth.create_session(uid)
                    st.query_params["s"] = token
                    db.log_event("signup", uid=uid, visitor=_visitor_id())
                    _activate_plant(user)
                    st.rerun()


def _auth_gate():
    if "uid" in st.session_state:
        db.set_shop(st.session_state["uid"])
        return
    token = st.query_params.get("s")
    user = auth.resolve_session(token)
    if user:
        _activate_plant(user)
        return
    _render_login()
    st.stop()


def _visitor_id():
    vid = st.session_state.get("_vid")
    if not vid:
        vid = uuid.uuid4().hex[:16]
        st.session_state["_vid"] = vid
    return vid


if not st.session_state.get("_visit_logged"):
    db.log_event("visit", uid=st.session_state.get("uid"),
                 visitor=_visitor_id())
    st.session_state["_visit_logged"] = True

_auth_gate()


# ============================================================ SIDEBAR (nav)
NAV = {
    "dash":  "Executive Dashboard",
    "obs":   "Obsolete Detection",
    "fcast": "Consumption Forecast",
    "opt":   "Criticality Optimizer",
    "pdm":   "Predictive Maintenance",
    "master": "Spare Master & Data",
    "ask":   "Ask AISync",
    "road":  "Implementation Roadmap",
}

with st.sidebar:
    st.markdown(
        f"<div class='nav-head'>Plant</div>"
        f"<div style='font-weight:600;margin-bottom:.5rem'>"
        f"{_esc(st.session_state.get('plant_name',''))}</div>",
        unsafe_allow_html=True)
    st.markdown("<div class='nav-head'>Menu</div>", unsafe_allow_html=True)
    page = st.radio(" ", list(NAV.keys()), format_func=lambda k: NAV[k],
                    label_visibility="collapsed")

    if st.session_state.get("_last_page") != page:
        db.log_event("pageview", uid=st.session_state.get("uid"),
                     visitor=_visitor_id(), detail=NAV[page])
        st.session_state["_last_page"] = page
    st.divider()
    if st.button("Load HPL demo data", use_container_width=True):
        seed_db(); st.session_state.pop("imported_file", None); st.rerun()

    if st.session_state.get("confirm_reset"):
        st.warning("This deletes ALL spares, consumption and stock. Sure?")
        cc = st.columns(2)
        if cc[0].button("Yes, erase", use_container_width=True):
            db.reset_db()
            st.session_state.pop("imported_file", None)
            st.session_state.pop("confirm_reset", None)
            st.rerun()
        if cc[1].button("Cancel", use_container_width=True):
            st.session_state.pop("confirm_reset", None); st.rerun()
    else:
        if st.button("Reset workspace", use_container_width=True):
            st.session_state["confirm_reset"] = True; st.rerun()

    st.divider()
    with st.expander("Account"):
        st.caption(f"Signed in as **{st.session_state.get('username','')}**")
        with st.form("change_pw"):
            op = st.text_input("Current password", type="password")
            np_ = st.text_input("New password (6+ chars)", type="password")
            if st.form_submit_button("Change password"):
                try:
                    auth.change_password(st.session_state["uid"], op, np_)
                    st.success("Password changed.")
                except auth.AuthError as e:
                    st.error(str(e))
        if st.button("Log out", use_container_width=True):
            auth.destroy_session(st.query_params.get("s"))
            st.query_params.clear()
            for k in ("uid", "username", "plant_name"):
                st.session_state.pop(k, None)
            st.rerun()

st.markdown(
    f"<div class='appbar'><div class='logo'>{LOGO_MARK}</div>"
    "<div><div class='brand-name'>AISync</div>"
    f"<div class='brand-sub'>{_esc(TAGLINE)}</div></div></div>",
    unsafe_allow_html=True)

DATA_SIG = db.data_signature()
have_data = int(DATA_SIG.split(":")[3]) > 0


def _need_data_hint():
    st.info("No spare master loaded yet. Click **Load HPL demo data** in the "
            "sidebar, or go to **Spare Master & Data** to upload your SAP export.")


# ---- cached analytics (rebuild only when the plant's data changes) --------
@st.cache_data(show_spinner=False)
def _rows_cached(shop_id, sig):
    """Report + spare enrichment in one pass. Streamlit reruns the whole
    script per click; caching on the data signature avoids re-hitting the
    remote DB and retraining the forecaster (~2s) on every interaction."""
    report = build_report()
    return spares.analyze(report=report)


@st.cache_data(show_spinner=False)
def _facts_cached(shop_id, sig):
    return spares.build_facts(rows=_rows_cached(shop_id, sig))


def _load_rows():
    return list(_rows_cached(st.session_state["uid"], DATA_SIG))


# ============================================================ PAGE: DASHBOARD
def page_dashboard():
    if not have_data:
        _need_data_hint(); return
    rows = _load_rows()
    pf = spares.portfolio(rows)

    m = st.columns(4)
    m[0].metric("Working capital blocked", spares.cr(pf["total_capital"]),
                help="On-hand stock × unit cost, across every spare line.")
    m[1].metric("Release opportunity", spares.cr(pf["release_opportunity"]),
                f"{pf['release_pct']:.0f}% of capital")
    m[2].metric("Obsolete / dead stock", spares.cr(pf["obsolete_value"]),
                f"{pf['obsolete_pct']:.0f}% · {pf['n_obsolete']} lines")
    m[3].metric("Critical spares at risk", len(pf["critical_at_risk"]),
                "reorder first", delta_color="inverse")

    st.caption("Every figure is computed from the plant's own consumption and "
               "stock — nothing is estimated or assumed.")

    c = st.columns([3, 2])
    with c[0]:
        st.subheader("Where the capital sits")
        bc = pd.DataFrame({
            "Criticality": ["Critical", "Essential", "Non-critical"],
            "Capital (₹ Cr)": [pf["by_criticality"]["critical"] / 1e7,
                               pf["by_criticality"]["essential"] / 1e7,
                               pf["by_criticality"]["non-critical"] / 1e7],
        }).set_index("Criticality")
        st.bar_chart(bc, height=260, color="#1F4E79")
        st.caption("Critical spares are strategic insurance — never trimmed. "
                   "The release opportunity comes from obsolete lines and "
                   "excess above AI-optimal levels on the rest.")
    with c[1]:
        st.subheader("Release opportunity")
        st.markdown(
            f"<div class='card'><h4>{spares.cr(pf['release_opportunity'])} "
            f"recoverable</h4>"
            f"<div style='color:#5B6879;font-size:.9rem'>"
            f"{spares.cr(pf['obsolete_value'])} obsolete/dead stock<br>"
            f"{spares.cr(pf['excess_value'])} excess above AI-optimal levels"
            f"</div></div>", unsafe_allow_html=True)
        if pf["shutdown_exposed"]:
            names = ", ".join(_esc(r["name"] or r["sku"])
                              for r in pf["shutdown_exposed"][:4])
            st.markdown(
                f"<div class='card'><h4 style='color:#B4543A'>"
                f"{len(pf['shutdown_exposed'])} high shutdown-risk spare(s)</h4>"
                f"<div style='color:#5B6879;font-size:.9rem'>{names}</div></div>",
                unsafe_allow_html=True)

    st.subheader("Plant-wide spare consumption")
    sales = db.get_sales()
    if sales:
        sdf = pd.DataFrame(sales)
        daily = sdf.groupby("date")["qty"].sum()
        st.line_chart(daily, height=240, color="#0E7C86")
        st.caption("Total spare units issued per day (maintenance draws cluster "
                   "on planned shutdown windows).")
    else:
        st.caption("No consumption logged yet.")

    st.subheader("Highest-capital spare lines")
    top = sorted(rows, key=lambda r: -r["capital"])[:10]
    st.dataframe(pd.DataFrame([{
        "Spare": r["name"] or r["sku"],
        "Equipment": r.get("equipment", ""),
        "Criticality": r.get("criticality", ""),
        "On hand": int(r["on_hand"]),
        "Capital": spares.cr(r["capital"]),
        "Status": ("Obsolete" if r["obsolete"] else
                   "Insurance" if r.get("insurance") else
                   f"Excess {spares.cr(r['excess_value'])}" if r["excess_value"] > 0
                   else "Optimal"),
    } for r in top]), use_container_width=True, hide_index=True)


# ============================================================ PAGE: OBSOLETE
def page_obsolete():
    if not have_data:
        _need_data_hint(); return
    rows = _load_rows()
    pf = spares.portfolio(rows)
    obs = spares.obsolete_rows(rows)

    m = st.columns(3)
    m[0].metric("Obsolete lines", pf["n_obsolete"])
    m[1].metric("Dead capital locked", spares.cr(pf["obsolete_value"]))
    m[2].metric("Share of total capital", f"{pf['obsolete_pct']:.0f}%")

    st.caption(f"Obsolete = no issue in over {spares.OBSOLETE_YEARS} years "
               "(critical strategic spares are exempt). These are candidates "
               "for redeployment, resale or write-down.")

    if not obs:
        st.success("No obsolete stock detected.")
        return
    st.dataframe(pd.DataFrame([{
        "Spare": r["name"] or r["sku"],
        "Equipment": r.get("equipment", ""),
        "Criticality": r.get("criticality", ""),
        "On hand": int(r["on_hand"]),
        "Years idle": (f"{r['age_years']:.1f}" if r.get("age_years") else "—"),
        "Locked capital": spares.cr(r["capital"]),
    } for r in obs]), use_container_width=True, hide_index=True)

    st.markdown("#### Recommended action")
    st.markdown(
        "- **Redeploy** to sister sites still running the equipment.\n"
        "- **Resell / return** superseded-spec items to OEMs or the surplus market.\n"
        "- **Write down** unrecoverable legacy stock to free the balance sheet.")


# ============================================================ PAGE: FORECAST
def page_forecast():
    if not have_data:
        _need_data_hint(); return
    rows = _load_rows()
    ai_rows = [r for r in rows if r["forecast"].get("ai_analysis")]

    st.subheader("Neural consumption forecaster")
    st.caption("A from-scratch neural net (numpy only), trained on the whole "
               "plant's issue history, learns each spare's trend, weekly "
               "maintenance rhythm and recent momentum. Intermittent capital "
               "spares route to Croston's method automatically.")

    if not ai_rows:
        st.info("Not enough consumption history for the neural model yet — "
                "spares are running on the explainable heuristic.")
        return

    rising = sorted((r for r in ai_rows
                     if r["forecast"]["ai_analysis"]["trend_dir"] == "rising"),
                    key=lambda r: -r["forecast"]["ai_analysis"]["trend_pct_month"])
    falling = sorted((r for r in ai_rows
                      if r["forecast"]["ai_analysis"]["trend_dir"] == "falling"),
                     key=lambda r: r["forecast"]["ai_analysis"]["trend_pct_month"])

    c = st.columns(2)
    with c[0]:
        st.markdown("**Consumption accelerating**")
        if rising:
            for r in rising[:5]:
                a = r["forecast"]["ai_analysis"]
                st.markdown(f"{_dot(DOT['high'])} **{_esc(r['name'] or r['sku'])}** "
                            f"&nbsp;+{a['trend_pct_month']:.0f}%/mo",
                            unsafe_allow_html=True)
        else:
            st.caption("Nothing trending up.")
    with c[1]:
        st.markdown("**Consumption easing**")
        if falling:
            for r in falling[:5]:
                a = r["forecast"]["ai_analysis"]
                st.markdown(f"{_dot(DOT['low'])} **{_esc(r['name'] or r['sku'])}** "
                            f"&nbsp;{a['trend_pct_month']:.0f}%/mo",
                            unsafe_allow_html=True)
        else:
            st.caption("Nothing fading.")

    import numpy as _np
    import altair as alt
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    stacked = _np.array([[r["forecast"]["ai_analysis"]["weekly_shape"][d]
                          for d in dows] for r in ai_rows])
    plant_week = stacked.sum(axis=0)
    busiest = dows[int(plant_week.argmax())]
    st.subheader("Weekly maintenance rhythm")
    st.markdown(f"Heaviest spare draw falls on **{busiest}** — the model has "
                "learned the plant's planned-shutdown window.")
    wk_df = pd.DataFrame({"Day": dows, "Predicted units": plant_week})
    chart = (alt.Chart(wk_df).mark_bar(color="#1F4E79")
             .encode(x=alt.X("Day:N", sort=dows, title=None),
                     y=alt.Y("Predicted units:Q", title=None))
             .properties(height=220))
    st.altair_chart(chart, use_container_width=True)

    st.subheader("Per-spare AI read")
    st.dataframe(pd.DataFrame([{
        "Spare": r["name"] or r["sku"],
        "Equipment": r.get("equipment", ""),
        "Forecast/day": round(r["forecast"]["daily_rate"], 3),
        "Trend/mo": f"{r['forecast']['ai_analysis']['trend_pct_month']:+.0f}%",
        "Momentum": f"{r['forecast']['ai_analysis']['momentum_pct']:+.0f}%",
        "Peak day": r["forecast"]["ai_analysis"]["busiest_day"],
    } for r in ai_rows]), use_container_width=True, hide_index=True)


# ============================================================ PAGE: OPTIMIZER
def page_optimize():
    if not have_data:
        _need_data_hint(); return
    rows = _load_rows()
    need = spares.reorder_rows(rows)

    st.subheader("Criticality-based service levels")
    st.caption("Higher-criticality spares are protected to a tighter service "
               "level, so their safety stock is sized for a rarer stockout — "
               "critical spares are never cut blindly to save cash.")
    st.table(pd.DataFrame([
        {"Criticality": "Critical", "Service level": "99.0%",
         "Meaning": "Compressor/furnace spares — a stockout can idle the plant"},
        {"Criticality": "Essential", "Service level": "95.0%",
         "Meaning": "Pumps, valves, motors — protected but not insurance-grade"},
        {"Criticality": "Non-critical", "Service level": "90.0%",
         "Meaning": "Consumables — trimmed hardest to release capital"},
    ]))

    st.subheader("Procurement priority — worst shutdown risk first")
    if not need:
        st.success("No replenishment needed right now.")
    else:
        total_spend = sum(r["reco_qty"] * r["unit_cost"] for r in need)
        st.markdown(f"**{len(need)} spare(s)** need replenishment · estimated "
                    f"procurement value **{spares.cr(total_spend)}**.")

        budget_cr = st.slider(
            "Procurement budget this cycle (₹ Cr)", 0.0,
            float(round(total_spend / 1e7 + 1, 1)),
            float(round(total_spend / 1e7 + 1, 1)), step=0.5,
            help="Drag down if capital is tight — AISync funds the highest "
                 "shutdown-risk spares first.")
        budget = budget_cr * 1e7

        chosen, deferred, spent = [], [], 0.0
        for r in need:
            cost = r["reco_qty"] * r["unit_cost"]
            if spent + cost <= budget:
                chosen.append(r); spent += cost
            else:
                deferred.append(r)

        mm = st.columns(3)
        mm[0].metric("Funded now", spares.cr(spent))
        mm[1].metric("Spares funded", len([r for r in chosen]))
        mm[2].metric("Deferred", len(deferred))

        def _reo_table(lst):
            return pd.DataFrame([{
                "Spare": r["name"] or r["sku"],
                "Equipment": r.get("equipment", ""),
                "Criticality": r.get("criticality", ""),
                "Type": "Insurance" if r.get("insurance") else "Demand",
                "Risk": r["risk"],
                "On hand": int(r["on_hand"]),
                "Order qty": int(r["reco_qty"]),
                "Value": spares.cr(r["reco_qty"] * r["unit_cost"]),
            } for r in lst])

        st.markdown("##### Fund these now")
        st.dataframe(_reo_table(chosen), use_container_width=True, hide_index=True)
        if deferred:
            st.markdown("##### Deferred to next cycle (raise budget to include)")
            st.dataframe(_reo_table(deferred), use_container_width=True,
                         hide_index=True)

    ins = [r for r in rows if r.get("insurance")]
    if ins:
        st.subheader("Insurance spares (strategic minimum)")
        st.caption("Ultra-expensive critical units (≥ ₹1 Cr each) are held to a "
                   "strategic minimum of "
                   f"{spares.INSURANCE_MIN} per train — never demand-forecast, "
                   "never flagged excess. One failure must not idle the train.")
        st.dataframe(pd.DataFrame([{
            "Spare": r["name"] or r["sku"],
            "Equipment": r.get("equipment", ""),
            "On hand": int(r["on_hand"]),
            "Strategic min": spares.INSURANCE_MIN,
            "Risk": r["risk"],
            "Unit cost": spares.cr(r["unit_cost"]),
        } for r in ins]), use_container_width=True, hide_index=True)


# ============================================================ PAGE: PREDICTIVE
def page_predictive():
    if not have_data:
        _need_data_hint(); return
    rows = _load_rows()
    pdm = spares.predictive_maintenance(rows)

    st.subheader("Predictive maintenance signals")
    st.caption("When a spare's consumption accelerates, the equipment it serves "
               "is often heading toward failure. AISync surfaces these early so "
               "you can reorder and plan intervention BEFORE a breakdown.")

    if not pdm:
        st.success("No accelerating-consumption signals right now — spare draw "
                   "is stable across the plant.")
        return

    for r in pdm:
        crit = r.get("criticality", "essential")
        st.markdown(
            f"<div class='card'><h4>{_dot(DOT['high'])} "
            f"{_esc(r['name'] or r['sku'])} &nbsp;{_crit_pill(crit)}</h4>"
            f"<div style='color:#5B6879;font-size:.9rem'>"
            f"Equipment: {_esc(r.get('equipment','') or 'unassigned')} &nbsp;·&nbsp; "
            f"last-week momentum <b>{r['momentum_pct']:+.0f}%</b> &nbsp;·&nbsp; "
            f"monthly trend <b>{r['trend_pct_month']:+.0f}%</b><br>"
            f"On hand {int(r['on_hand'])} · daily draw "
            f"{r['reorder']['daily_rate']:.2f} · order signal "
            f"<b>{int(r['reco_qty'])}</b> unit(s)</div></div>",
            unsafe_allow_html=True)
    st.caption("Signal = consumption momentum or trend above +12%. Investigate "
               "the served equipment and stage the spare ahead of the shutdown.")


# ============================================================ PAGE: MASTER/DATA
def _upload_flow():
    up = st.file_uploader("Upload SAP / Excel / CSV export",
                          type=["xlsx", "xls", "csv"], key="inv_upload")
    file_tag = (up.name, up.size) if up is not None else None
    already = st.session_state.get("imported_file") == file_tag
    if up is None or already:
        return
    st.markdown("#### Reading your export")
    ad = TabularAdapter()
    df = ad.read(up)
    st.write("First rows detected:")
    st.dataframe(df.head(8), use_container_width=True)
    mapping = ad.suggest_mapping(df, CANON_FIELDS)
    nice = {"sku": "Material code", "name": "Material description",
            "date": "Posting date", "qty": "Quantity issued",
            "stock": "Unrestricted stock", "unit_cost": "Moving avg price"}
    st.write("**Columns auto-mapped.** Correct any that are wrong:")
    cols = ["(none)"] + list(df.columns)
    corrected = {}
    g = st.columns(3)
    for i, f in enumerate(["sku", "name", "date", "qty", "stock", "unit_cost"]):
        with g[i % 3]:
            guess = mapping[f]["column"]
            idx = cols.index(guess) if guess in cols else 0
            tick = "✓ " if guess else ""
            sel = st.selectbox(f"{tick}{nice[f]}", cols, index=idx, key=f"m_{f}")
            if sel != "(none)":
                corrected[f] = {"column": sel, "confidence": 1.0}
    if st.button("Looks right — load spare master", type="primary"):
        b = ad.normalize(df, corrected)
        if not b.products:
            st.error("Couldn't read any spares — check the **Material code** column.")
            for w in b.warnings:
                st.info(w)
            return
        db.upsert_products(b.products)
        if b.sales:     db.insert_sales(b.sales)
        if b.inventory: db.upsert_inventory(b.inventory)
        if b.suppliers: db.upsert_suppliers(b.suppliers)
        st.session_state["imported_file"] = file_tag
        st.success(f"Loaded {len(b.products)} spares and {len(b.sales)} "
                   "consumption records.")
        st.rerun()


def page_master():
    st.subheader("Spare master & data")
    st.caption("Record spare issues and receipts, set stock counts, or sync a "
               "SAP export. Auto column-mapping handles messy plant exports.")

    products = db.get_products()

    tab_issue, tab_stock, tab_upload, tab_add = st.tabs(
        ["Record issue / receipt", "Set stock counts",
         "Upload SAP export", "Add a spare"])

    # ---- record consumption (issues) + receipts ----
    with tab_issue:
        if not products:
            _need_data_hint()
        else:
            st.markdown("##### Record spare issues (consumption)")
            st.caption("Enter how many of each spare were issued to maintenance. "
                       "Stock deducts automatically.")
            with st.form("issue_form"):
                issued = {}
                inv = {i["sku"]: i["on_hand"] for i in db.get_inventory()}
                for p in products:
                    cc = st.columns([4, 2])
                    cc[0].markdown(f"**{p.get('name') or p['sku']}**  \n"
                                   f"On hand: {int(inv.get(p['sku'], 0) or 0)}")
                    issued[p["sku"]] = cc[1].number_input(
                        "Issued", min_value=0, step=1, value=0,
                        key=f"iss_{p['sku']}")
                if st.form_submit_button("Save issues", type="primary"):
                    lines = [(s, q) for s, q in issued.items() if q and q > 0]
                    db.record_sales_bulk(lines)
                    st.success(f"Recorded {len(lines)} issue(s).") if lines \
                        else st.info("Nothing entered.")
                    st.rerun()

            st.divider()
            st.markdown("##### Receive stock (procurement in)")
            with st.form("recv_form"):
                recv = {}
                for p in products:
                    cc = st.columns([4, 2])
                    cc[0].markdown(f"**{p.get('name') or p['sku']}**")
                    recv[p["sku"]] = cc[1].number_input(
                        "Received", min_value=0, step=1, value=0,
                        key=f"rcv_{p['sku']}")
                if st.form_submit_button("Add to stock"):
                    lines = [(s, q) for s, q in recv.items() if q and q > 0]
                    db.receive_stock_bulk(lines)
                    st.success(f"Received {len(lines)} line(s).") if lines \
                        else st.info("Nothing entered.")
                    st.rerun()

    # ---- set stock counts ----
    with tab_stock:
        if not products:
            _need_data_hint()
        else:
            st.markdown("##### Set current on-hand stock")
            inv = {i["sku"]: i["on_hand"] for i in db.get_inventory()}
            seed = [{"Spare": p.get("name") or p["sku"], "_sku": p["sku"],
                     "On hand": int(inv.get(p["sku"], 0) or 0)} for p in products]
            edited = st.data_editor(
                seed, use_container_width=True, hide_index=True, key="stock_grid",
                column_config={
                    "Spare": st.column_config.TextColumn(disabled=True),
                    "_sku": None,
                    "On hand": st.column_config.NumberColumn(min_value=0, step=1),
                })
            if st.button("Save stock counts", type="primary"):
                db.upsert_inventory([{"sku": r["_sku"], "stock": r["On hand"]}
                                     for r in edited])
                st.success("Stock updated"); st.rerun()

    # ---- upload SAP export ----
    with tab_upload:
        _upload_flow()
        st.caption("No export handy? Generate a deliberately messy sample to "
                   "test the auto-mapping:")
        if st.button("Make a sample SAP export"):
            p = write_messy_excel()
            with open(p, "rb") as f:
                st.download_button("Download sample.xlsx", f,
                                   file_name="sap_spare_issues.xlsx")

    # ---- add a single spare ----
    with tab_add:
        with st.form("manual"):
            c = st.columns(2)
            sku = c[0].text_input("Material code (e.g. CGC-ROTOR)")
            name = c[1].text_input("Description (e.g. Cracked Gas Compressor Rotor)")
            c2 = st.columns(3)
            stock = c2[0].number_input("On hand", min_value=0.0, value=0.0)
            cost = c2[1].number_input("Unit cost (₹)", min_value=0.0, value=0.0)
            lead = c2[2].number_input("Lead time (days)", min_value=0.0, value=90.0)
            c3 = st.columns(2)
            crit = c3[0].selectbox("Criticality",
                                   ["critical", "essential", "non-critical"],
                                   index=1)
            equip = c3[1].text_input("Equipment / tag")
            if st.form_submit_button("Save spare", type="primary") and sku:
                db.upsert_products([{"sku": sku, "name": name, "unit_cost": cost,
                                     "criticality": crit, "equipment": equip}])
                db.upsert_inventory([{"sku": sku, "stock": stock}])
                db.upsert_suppliers([{"sku": sku, "lead_time_days": lead,
                                      "reliability": 0.95}])
                st.success(f"Saved {name or sku}"); st.rerun()


# ============================================================ PAGE: ASK
def page_ask():
    st.subheader("Ask AISync")
    st.caption("Ask about blocked capital, obsolete stock, what to reorder, or "
               "any spare's forecast. Every answer is computed from the plant's "
               "real data — no hallucinated numbers.")

    if not have_data:
        st.info("Load the spare master first, then ask away.")
        return

    suggestions = [
        "How much working capital is blocked?",
        "Which spares are obsolete?",
        "How much can we release?",
        "What should we reorder first?",
        "Which critical spares are at risk?",
    ]
    cols = st.columns(len(suggestions))
    picked = None
    for i, s in enumerate(suggestions):
        if cols[i].button(s, key=f"ask_sug_{i}", use_container_width=True):
            picked = s

    q = st.chat_input("Ask about the plant's spare inventory…")
    question = picked or q

    hist = st.session_state.setdefault("ask_history", [])
    if question:
        with st.spinner("Computing from plant data…"):
            cards = _facts_cached(st.session_state["uid"], DATA_SIG)
            from core.assistant import answer as _answer
            ans = _answer(question, cards=cards)
        hist.append((question, ans))

    if hist and st.button("Clear chat", key="ask_clear"):
        st.session_state["ask_history"] = []
        st.rerun()

    def _md(txt):
        return (txt or "").replace("~", "\\~")

    for uq, ua in hist:
        with st.chat_message("user"):
            st.markdown(_md(uq))
        with st.chat_message("assistant"):
            st.markdown(_md(ua))


# ============================================================ PAGE: ROADMAP
def page_roadmap():
    st.subheader("Implementation roadmap")
    st.caption("A phased, SAP-integrated rollout — start read-only on a data "
               "export, earn trust, then close the loop with procurement.")

    phases = [
        ("Phase 1 · Data foundation",
         "Ingest the spare master and 3–5 years of issue history from SAP MM "
         "(read-only export). Auto-map messy columns, clean units and dates, "
         "establish the working-capital baseline in ₹Cr."),
        ("Phase 2 · Obsolescence & criticality",
         "Tag every line by criticality (critical / essential / non-critical) "
         "and flag obsolete/dead stock (>5 yrs no movement). Surface the first "
         "release opportunity for finance sign-off."),
        ("Phase 3 · AI forecasting & optimization",
         "Train the neural consumption forecaster plant-wide; set "
         "criticality-based service levels and insurance-spare minimums. "
         "Produce reorder points and excess-release recommendations."),
        ("Phase 4 · Predictive maintenance link",
         "Correlate accelerating spare consumption with equipment health to "
         "flag likely failures early, feeding the maintenance planning module."),
        ("Phase 5 · Closed-loop SAP integration",
         "Write reorder proposals back to SAP as purchase requisitions; live "
         "two-way sync so stock, issues and lead times stay current with no "
         "manual export."),
    ]
    for title, body in phases:
        st.markdown(
            f"<div class='card'><h4>{_esc(title)}</h4>"
            f"<div style='color:#5B6879;font-size:.92rem'>{_esc(body)}</div></div>",
            unsafe_allow_html=True)

    st.subheader("Why AISync")
    cc = st.columns(3)
    facts = [
        ("Grounded, not guessed",
         "Every ₹Cr figure is computed from the plant's own data. The assistant "
         "cannot invent numbers."),
        ("From-scratch AI",
         "The forecaster is a numpy-only neural net with cross-spare pooling — "
         "no paid APIs, fully inspectable, runs on plant infrastructure."),
        ("Reliability-first",
         "Critical and insurance spares are protected to tighter service levels; "
         "capital is released only from obsolete and genuinely excess stock."),
    ]
    for i, (h, b) in enumerate(facts):
        cc[i].markdown(
            f"<div class='card'><h4>{_esc(h)}</h4>"
            f"<div style='color:#5B6879;font-size:.9rem'>{_esc(b)}</div></div>",
            unsafe_allow_html=True)


# ============================================================ DISPATCH
PAGES = {
    "dash": page_dashboard, "obs": page_obsolete, "fcast": page_forecast,
    "opt": page_optimize, "pdm": page_predictive, "master": page_master,
    "ask": page_ask, "road": page_roadmap,
}
PAGES[page]()
