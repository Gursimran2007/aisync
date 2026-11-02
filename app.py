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
from core import profile as user_profile
from core import strategist
from core import company

st.set_page_config(page_title="AISync — Spare Inventory Optimization",
                   page_icon="◆", layout="wide")


@st.cache_resource
def _init_auth():
    """Create the auth tables once per server process (not per rerun)."""
    auth.init()
    return True


_init_auth()

# In-brand mark: a hexagon "spare" frame with two synced flow-arcs, a pulsing
# AI core and an orbiting node — a quiet motion-of-flow motif (SMIL animates
# even when injected as innerHTML, so it runs without external JS).
LOGO_MARK = (
    "<svg width='34' height='34' viewBox='0 0 40 40' fill='none' "
    "xmlns='http://www.w3.org/2000/svg' role='img' aria-label='AISync'>"
    "<defs>"
    "<linearGradient id='asStroke' x1='0' y1='0' x2='40' y2='40' "
    "gradientUnits='userSpaceOnUse'>"
    "<stop offset='0' stop-color='#EAF3FF'/>"
    "<stop offset='1' stop-color='#BFE0FF'/></linearGradient></defs>"
    # hexagon frame — the plant / containment (centered at 20,20)
    "<path d='M20 3.75 33.75 11.875V28.125L20 36.25 6.25 28.125V11.875Z' "
    "stroke='#fff' stroke-opacity='.32' stroke-width='1.6' fill='none'/>"
    # two interlocking sync arcs — a closed optimization loop around the core
    "<g stroke='url(#asStroke)' stroke-width='2.6' stroke-linecap='round' "
    "fill='none'>"
    "<path d='M20 10.6A9.4 9.4 0 0 1 29.4 20'/>"
    "<path d='M20 29.4A9.4 9.4 0 0 1 10.6 20'/></g>"
    # directional heads that make the loop read as continuous flow
    "<path d='M29.4 20 26.9 16.1 31.3 16.6Z' fill='#fff'/>"
    "<path d='M10.6 20 13.1 23.9 8.7 23.4Z' fill='#fff'/>"
    # pulsing core = the live signal
    "<circle cx='20' cy='20' r='3.5' fill='#fff'>"
    "<animate attributeName='r' values='3.1;4.1;3.1' dur='2.8s' "
    "repeatCount='indefinite'/>"
    "<animate attributeName='fill-opacity' values='1;.72;1' dur='2.8s' "
    "repeatCount='indefinite'/></circle>"
    "</svg>"
)


def inject_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
      :root{
        /* cool-grey base — 'grey is the new black' (Apple system greys).
           The canvas is a real, visible grey so white cards float on it; the
           grey is the field, blue is the highlight. */
        --bg:#DDE0E6; --panel:#E4E7EC; --surface:#FFFFFF; --border:#BFC5CF; --border-2:#D2D7DF;
        --text:#1D1D1F; --muted:#6E6E73; --accent:#1F4E79; --accent-2:#2C6699;
        --accent-soft:#E9F0F7; --teal:#0E7C86; --display:'Space Grotesk',sans-serif;
        /* slate-grey secondary accent — contrasts the blue so metadata,
           eyebrows and neutral tags read grey while blue stays the highlight */
        --slate:#7E8896; --slate-2:#586171; --slate-soft:#EEF0F3;
        --slate-line:#CBD1DA; --slate-grad-a:#9AA3B2; --slate-grad-b:#6B7482;
        /* large, smooth corners read as 'premium app', not 'database software' */
        --radius:18px; --radius-sm:12px; --radius-lg:22px;
        /* glass material */
        --glass:rgba(255,255,255,.70); --glass-strong:rgba(255,255,255,.82);
        --glass-brd:rgba(255,255,255,.65); --hair:rgba(60,60,67,.12);
        /* multi-layered, physical depth (ambient + contact + key light) */
        --shadow-sm:0 1px 1px rgba(20,27,38,.04), 0 2px 6px rgba(20,27,38,.05);
        --shadow-md:0 2px 4px rgba(20,27,38,.05), 0 10px 24px rgba(20,27,38,.08);
        --shadow-lg:0 8px 16px rgba(20,27,38,.08), 0 24px 56px rgba(20,27,38,.14);
        --shadow-glass:0 1px 0 rgba(255,255,255,.6) inset,
                       0 1px 2px rgba(20,27,38,.04),
                       0 12px 30px rgba(20,27,38,.10);
        --ease:cubic-bezier(.4,0,.2,1);
        --spring:cubic-bezier(.34,1.56,.64,1);
        --apple:cubic-bezier(.25,1,.5,1);
      }
      html, body, [class*="css"] { font-family:'Inter',sans-serif; color:var(--text);
        -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
      html{ scroll-behavior:smooth; }
      .stApp { background:
        /* faint engineering dot-grid — kills the 'blank paper' feel */
        radial-gradient(circle at 1px 1px, rgba(31,78,121,.055) 1px, transparent 0),
        /* soft ambient light blobs give the page depth and colour */
        radial-gradient(760px 520px at 88% -6%, rgba(76,147,212,.20) 0%, transparent 60%),
        radial-gradient(680px 520px at -6% 4%, rgba(14,124,134,.12) 0%, transparent 55%),
        /* cool slate-grey blobs carry the grey field across the whole canvas */
        radial-gradient(820px 620px at 8% 96%, rgba(110,122,138,.32) 0%, transparent 58%),
        radial-gradient(980px 760px at 96% 60%, rgba(116,128,144,.26) 0%, transparent 60%),
        var(--bg);
        background-attachment:fixed;
        background-size:22px 22px, 150% 150%, 150% 150%, 150% 150%, 150% 150%, 100% 100%;
        animation:ssDrift 26s ease-in-out infinite alternate; }
      /* fluid type scale — perfectly sized on any screen */
      h1{ font-size:clamp(1.7rem,1.2rem + 1.6vw,2.4rem); }
      h2{ font-size:clamp(1.35rem,1.05rem + 1.1vw,1.85rem); }
      h3{ font-size:clamp(1.12rem,.95rem + .7vw,1.4rem); }
      header[data-testid="stHeader"]{ background:transparent; }
      [data-testid="stToolbar"]{ display:none; }

      /* ---- motion system (Apple-like: content flows in, staggered) ---- */
      @keyframes ssRise{ from{opacity:0; transform:translateY(8px);} to{opacity:1; transform:none;} }
      @keyframes ssFadeUp{ from{opacity:0; transform:translateY(22px) scale(.985);}
                           to{opacity:1; transform:none;} }
      @keyframes ssDrift{
        from{background-position:0 0, 0% 0%, 0% 0%, 0% 0%, 0% 0%, 0 0;}
        to{  background-position:0 0, 100% 60%, 40% 100%, 25% 80%, 70% 30%, 0 0;} }
      @keyframes ssShine{ 0%{transform:translateX(-120%) skewX(-18deg);}
                          60%,100%{transform:translateX(220%) skewX(-18deg);} }
      @keyframes ssPop{ from{opacity:0; transform:scale(.9);} to{opacity:1; transform:none;} }
      /* ---- 3D motion: float + gentle axis rotation (GPU transforms, no JS) ---- */
      @keyframes ssFloat3d{
        0%{   transform:translateY(0)     rotateX(6deg)  rotateY(-14deg); }
        50%{  transform:translateY(-7px)  rotateX(-4deg) rotateY(12deg); }
        100%{ transform:translateY(0)     rotateX(6deg)  rotateY(-14deg); }
      }
      @keyframes ssSpin3d{ to{ transform:rotateY(360deg); } }
      @keyframes ssTilt3d{
        0%{   transform:perspective(900px) rotateX(3deg)  rotateY(-5deg); }
        50%{  transform:perspective(900px) rotateX(-3deg) rotateY(5deg); }
        100%{ transform:perspective(900px) rotateX(3deg)  rotateY(-5deg); }
      }
      .main .block-container{ animation:ssRise .3s var(--ease) both; }
      /* stagger the primary content blocks as they enter */
      .main .block-container > div > div > [data-testid="stVerticalBlock"] > div{
        animation:ssFadeUp .5s var(--ease) both;
      }
      [data-testid="stMetric"]{ animation:ssFadeUp .55s var(--spring) both; }
      div[data-testid="column"]:nth-child(1) [data-testid="stMetric"]{ animation-delay:.02s; }
      div[data-testid="column"]:nth-child(2) [data-testid="stMetric"]{ animation-delay:.09s; }
      div[data-testid="column"]:nth-child(3) [data-testid="stMetric"]{ animation-delay:.16s; }
      div[data-testid="column"]:nth-child(4) [data-testid="stMetric"]{ animation-delay:.23s; }
      .card{ animation:ssFadeUp .5s var(--ease) both; }
      @media (prefers-reduced-motion: reduce){
        *, .stApp{ animation:none !important; transition:none !important; }
      }
      [data-testid="stSidebar"][aria-expanded="false"]{
        transform:none !important;
        width:46px !important; min-width:46px !important;
        overflow:hidden !important;
        background:var(--panel); border-right:1px solid var(--border);
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
      .block-container { padding-top:2.8rem; max-width:1240px; }
      /* vertical rhythm — Apple-style generous gap between stacked blocks */
      .main .block-container > div > div > [data-testid="stVerticalBlock"]{ gap:1.6rem; }
      /* keep the horizontal gap at 1rem — Streamlit's column flex-basis is
         calc(25% - 16px), so a wider gap overflows and wraps the 4th card */
      [data-testid="stHorizontalBlock"]{ gap:1rem; }
      h1,h2,h3 { font-family:var(--display); letter-spacing:-.022em; font-weight:600; }
      h4 { letter-spacing:-.015em; font-weight:600; }

      .appbar{
        position:relative;
        display:flex; align-items:center; gap:22px;
        padding:10px 0 26px; margin-bottom:30px;
        animation:ssRise .45s var(--ease) both;
        perspective:1100px; perspective-origin:30% 40%;
      }
      /* soft gradient divider that fades out at both edges + faint drop shadow */
      .appbar::after{
        content:""; position:absolute; left:0; right:0; bottom:0; height:1px;
        background:linear-gradient(90deg, transparent 0%,
                   rgba(31,78,121,.28) 22%, rgba(31,78,121,.28) 78%, transparent 100%);
        box-shadow:0 6px 14px -8px rgba(20,27,38,.22);
      }
      .appbar .logo{
        width:62px; height:62px; border-radius:18px; flex:0 0 62px;
        position:relative; overflow:hidden;
        background:
          radial-gradient(120% 120% at 25% 15%, #4C93D4 0%, transparent 60%),
          linear-gradient(150deg, #2E6DA8 0%, var(--accent) 46%, #0E2A45 100%);
        display:flex; align-items:center; justify-content:center;
        box-shadow:0 10px 26px rgba(31,78,121,.40),
                   0 2px 6px rgba(20,27,38,.18),
                   inset 0 1px 0 rgba(255,255,255,.34),
                   inset 0 -4px 10px rgba(0,0,0,.20);
        /* real 3D: the badge is a solid slab that floats and turns in space */
        transform-style:preserve-3d;
        animation:ssFloat3d 7s ease-in-out infinite;
        transition:box-shadow .35s var(--ease), animation-play-state .35s;
      }
      .appbar .logo::before{
        content:""; position:absolute; inset:0; transform:translateZ(-1px);
        background:radial-gradient(70% 55% at 50% 120%, rgba(76,147,212,.55), transparent 70%);
      }
      .appbar .logo::after{
        content:""; position:absolute; top:0; left:-20%; width:45%; height:100%;
        transform:translateZ(6px);
        background:linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
        animation:ssShine 6s var(--ease) 1.4s infinite;
      }
      /* lift the SVG toward the viewer so the mark sits above the slab face */
      .appbar .logo svg{ transform:translateZ(14px); }
      .appbar .logo:hover{
        animation-play-state:paused;
        transform:perspective(1100px) rotateY(24deg) rotateX(-8deg) translateZ(20px) scale(1.05);
        box-shadow:-18px 22px 40px rgba(20,27,38,.28),
                   0 2px 6px rgba(20,27,38,.18),
                   inset 0 1px 0 rgba(255,255,255,.40); }
      .appbar .logo svg{ display:block; position:relative; z-index:1; }
      .appbar .brand-wrap{ display:flex; flex-direction:column; gap:2px; }
      .appbar .brand-name{
        font-family:var(--display);
        font-size:clamp(1.9rem,1.5rem + 1.3vw,2.5rem); font-weight:700;
        line-height:1.0; letter-spacing:-.035em;
        /* dark-blue -> mid-blue gradient that echoes the logo icon */
        background:linear-gradient(96deg, #0B2540 0%, #17436E 38%,
                   var(--accent) 66%, #2E6DA8 100%);
        -webkit-background-clip:text; background-clip:text;
        -webkit-text-fill-color:transparent; color:var(--accent);
      }
      .appbar .brand-name .tm{
        -webkit-text-fill-color:var(--muted); color:var(--muted);
        font-size:.9rem; font-weight:600; vertical-align:super;
        margin-left:2px; letter-spacing:0;
      }
      /* crisper subtitle: darker ink + roomier line-height for readability */
      .appbar .brand-sub{ font-size:.96rem; color:#4A5563; margin-top:3px;
        line-height:1.5; letter-spacing:.004em; max-width:62ch; }

      [data-testid="stMetric"]{
        background:var(--glass);
        -webkit-backdrop-filter:blur(20px) saturate(180%);
        backdrop-filter:blur(20px) saturate(180%);
        border:1px solid var(--glass-brd); border-radius:var(--radius);
        padding:20px 22px; box-shadow:var(--shadow-glass);
        position:relative; overflow:hidden;
        /* 3D-ready: give the card its own perspective + depth stacking */
        transform:perspective(900px);
        transform-style:preserve-3d;
        transition:transform .4s var(--spring), box-shadow .4s var(--apple);
      }
      [data-testid="stMetric"]::before{
        content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
        background:linear-gradient(var(--accent-2), var(--accent)); opacity:.9;
        transition:transform .4s var(--spring);
      }
      /* 3D lift — the card tilts back in space and rises toward the viewer */
      [data-testid="stMetric"]:hover{
        transform:perspective(900px) rotateX(7deg) rotateY(-6deg)
                  translateY(-6px) translateZ(24px);
        box-shadow:-14px 26px 44px rgba(20,27,38,.16),
                   0 8px 16px rgba(20,27,38,.08);
        border-color:rgba(255,255,255,.85);
      }
      /* push the accent bar + value forward so depth is visible on hover */
      [data-testid="stMetric"]:hover::before{ transform:translateZ(30px); }
      [data-testid="stMetric"] [data-testid="stMetricValue"]{
        transition:transform .4s var(--spring); transform:translateZ(0); }
      [data-testid="stMetric"]:hover [data-testid="stMetricValue"]{
        transform:translateZ(40px); }
      [data-testid="stMetricLabel"] p{
        font-size:.78rem !important; font-weight:700; letter-spacing:.055em;
        text-transform:uppercase; color:#3D4550;
      }
      [data-testid="stMetricValue"]{ font-weight:680;
        font-size:clamp(1.5rem,1.2rem + .9vw,1.9rem); letter-spacing:-.02em; }
      [data-testid="stMetricDelta"]{ font-size:.8rem; font-weight:650; gap:2px; }
      [data-testid="stMetricDelta"] svg{ height:1em; width:1em; }

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
      /* Reset workspace = destructive ghost: quiet grey outline that turns
         red on hover to signal it wipes data. */
      .st-key-btn_reset_ws button{
        background:transparent; border:1px solid var(--border);
        color:var(--muted); box-shadow:none;
      }
      .st-key-btn_reset_ws button:hover{
        background:#FCEDEA; border-color:#E0A99B; color:#B4351F;
        transform:none; box-shadow:none;
      }

      [data-testid="stSidebar"]{ background:linear-gradient(180deg, var(--panel), #DBDFE5);
        border-right:1px solid var(--border); }
      [data-testid="stSidebar"] .nav-head{
        font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
        color:var(--muted); padding:2px 6px 6px;
      }
      [data-testid="stSidebar"] [role="radiogroup"]{ gap:3px; }
      [data-testid="stSidebar"] [role="radiogroup"] label{
        display:flex; align-items:center; width:100%; border-radius:12px;
        padding:9px 14px; margin:0; line-height:1.2;
        cursor:pointer; font-weight:500; font-size:.92rem; color:var(--muted);
        border-left:4px solid transparent;
        transition:background .2s var(--apple), color .2s var(--apple),
                   border-color .2s var(--apple), transform .24s var(--spring);
      }
      [data-testid="stSidebar"] [role="radiogroup"] label p{ margin:0; }
      /* clean minimalist line-icons (Lucide/Feather), one per menu item.
         Rendered as a CSS mask so the glyph inherits the label's text colour —
         muted when idle, accent when hovered or active. */
      [data-testid="stSidebar"] [role="radiogroup"] label::before{
        content:""; flex:0 0 18px; width:18px; height:18px; margin-right:11px;
        background-color:currentColor;
        -webkit-mask:var(--ic) center/contain no-repeat;
        mask:var(--ic) center/contain no-repeat;
        opacity:.85; transition:opacity .2s var(--apple);
      }
      /* smooth pale-blue wash on hover for inactive items */
      [data-testid="stSidebar"] [role="radiogroup"] label:hover{
        background:#F0F5FB; color:var(--accent-2); }
      [data-testid="stSidebar"] [role="radiogroup"] label:hover::before{ opacity:1; }
      /* active: soft blue tint + bold blue left-border accent (border-l-4) */
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
        background:var(--accent-soft); border-left-color:var(--accent);
        box-shadow:0 1px 2px rgba(20,27,38,.05);
        color:var(--accent); font-weight:600;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{ color:var(--accent); font-weight:600; }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked)::before{ opacity:1; }
      [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child{ display:none; }
      /* per-item icon assignments (order matches the NAV dict) */
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(1){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='7' height='9'/%3E%3Crect x='14' y='3' width='7' height='5'/%3E%3Crect x='14' y='12' width='7' height='9'/%3E%3Crect x='3' y='16' width='7' height='5'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(2){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='2' y='4' width='20' height='5' rx='1'/%3E%3Cpath d='M4 9v10a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9'/%3E%3Cpath d='M10 13h4'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(3){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='22 7 13.5 15.5 8.5 10.5 2 17'/%3E%3Cpolyline points='16 7 22 7 22 13'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(4){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='4' y1='21' x2='4' y2='14'/%3E%3Cline x1='4' y1='10' x2='4' y2='3'/%3E%3Cline x1='12' y1='21' x2='12' y2='12'/%3E%3Cline x1='12' y1='8' x2='12' y2='3'/%3E%3Cline x1='20' y1='21' x2='20' y2='16'/%3E%3Cline x1='20' y1='12' x2='20' y2='3'/%3E%3Cline x1='1' y1='14' x2='7' y2='14'/%3E%3Cline x1='9' y1='8' x2='15' y2='8'/%3E%3Cline x1='17' y1='16' x2='23' y2='16'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(5){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='22 12 18 12 15 21 9 3 6 12 2 12'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(6){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cellipse cx='12' cy='5' rx='9' ry='3'/%3E%3Cpath d='M3 5v14a9 3 0 0 0 18 0V5'/%3E%3Cpath d='M3 12a9 3 0 0 0 18 0'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(7){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 1 1 21 11.5z'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(8){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6'/%3E%3Cline x1='8' y1='2' x2='8' y2='18'/%3E%3Cline x1='16' y1='6' x2='16' y2='22'/%3E%3C/svg%3E"); }
      [data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(9){ --ic:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z'/%3E%3Cpath d='M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'/%3E%3C/svg%3E"); }

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

      /* domain callout cards — glass material */
      .card{ background:var(--glass);
        -webkit-backdrop-filter:blur(20px) saturate(180%);
        backdrop-filter:blur(20px) saturate(180%);
        border:1px solid var(--glass-brd); border-radius:var(--radius);
        padding:20px 22px; box-shadow:var(--shadow-glass); margin-bottom:14px; }
      .card h4{ margin:.1rem 0 .3rem; }
      .pill{ display:inline-block; padding:2px 9px; border-radius:20px;
        font-size:.72rem; font-weight:600; letter-spacing:.02em;
        white-space:nowrap; }
      .pill-crit{ background:#FBE7E1; color:#B4543A; }
      .pill-ess{ background:#FDF3DF; color:#9A7420; }
      .pill-non{ background:#E7EFF7; color:#2C6699; }
      /* status palette — muted, readable, WCAG-AA on white, never neon */
      .pill-ok{ background:#E6F1EA; color:#356045; }
      .pill-warn{ background:#FBF0D9; color:#845F16; }
      .pill-danger{ background:#F7E2DC; color:#9C3F2A; }
      .pill-info{ background:#E4EEF9; color:#255E92; }
      .pill-neutral{ background:#EDF1F6; color:#54626F; }
      .pill .pdot{ width:6px; height:6px; border-radius:50%; display:inline-block;
        margin-right:5px; vertical-align:middle; background:currentColor; }

      .card{ transform:perspective(1000px); transform-style:preserve-3d;
        transition:transform .4s var(--spring), box-shadow .4s var(--apple); }
      .card:hover{ box-shadow:-12px 22px 40px rgba(20,27,38,.16),
                   0 6px 14px rgba(20,27,38,.08);
        transform:perspective(1000px) rotateX(5deg) rotateY(-5deg)
                  translateY(-4px) translateZ(16px); }

      /* ---- premium read-only data table (sticky header, zebra, hover) ---- */
      .ptable-wrap{ border:1px solid var(--border); border-radius:var(--radius);
        overflow:auto; max-height:540px; background:var(--surface);
        box-shadow:var(--shadow-sm); margin-bottom:12px;
        animation:ssFadeUp .5s var(--ease) both; }
      .ptable{ width:100%; border-collapse:separate; border-spacing:0;
        font-size:.9rem; }
      .ptable thead th{ position:sticky; top:0; z-index:2; background:#F6FAFE;
        text-align:left; color:var(--muted); font-size:.7rem; font-weight:700;
        letter-spacing:.05em; text-transform:uppercase; padding:11px 14px;
        border-bottom:1px solid var(--border); white-space:nowrap; }
      .ptable tbody td{ padding:10px 14px; border-bottom:1px solid var(--border-2);
        color:var(--text); vertical-align:middle; }
      .ptable tbody tr{ transition:background .12s var(--ease); }
      .ptable tbody tr:nth-child(even){ background:#FAFCFE; }
      .ptable tbody tr:hover{ background:var(--accent-soft); }
      .ptable tbody tr:last-child td{ border-bottom:none; }
      .ptable td.num, .ptable th.num{ text-align:right; white-space:nowrap;
        font-variant-numeric:tabular-nums; font-feature-settings:"tnum"; }
      .ptable td:first-child{ font-weight:600; color:#1B2733; }

      /* tabular figures everywhere numbers matter -> columns line up */
      [data-testid="stMetricValue"]{ font-variant-numeric:tabular-nums;
        font-feature-settings:"tnum"; }

      /* ---- responsive: tablet on the floor vs desktop in the office ---- */
      @media (max-width:1024px){
        .block-container{ padding-left:1.1rem; padding-right:1.1rem; }
        .appbar .logo{ width:54px; height:54px; flex:0 0 54px; }
        .appbar .brand-name{ font-size:1.85rem; }
        [data-testid="stMetricValue"]{ font-size:1.42rem; }
        .ptable{ font-size:.85rem; }
        .ptable thead th, .ptable tbody td{ padding:9px 11px; }
      }
      @media (max-width:680px){
        .appbar .brand-sub{ display:none; }
        .brief{ padding:16px; } .brief h3{ font-size:1.08rem; }
      }

      /* manager action band — the "what do I do this week" headline */
      .brief{ position:relative; overflow:hidden; margin:2px 0 28px;
        border:1px solid #CFE0F0; border-radius:16px; padding:20px 24px;
        background:linear-gradient(120deg, #F3F8FD 0%, #EAF2FB 55%, #E4EEF9 100%);
        box-shadow:var(--shadow-sm); animation:ssFadeUp .55s var(--ease) both; }
      .brief::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
        background:linear-gradient(var(--accent-2), var(--accent)); }
      .brief::after{ content:""; position:absolute; top:0; left:0; width:40%; height:100%;
        background:linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
        animation:ssShine 7s var(--ease) 1s infinite; }
      .brief .eyebrow{ font-size:.72rem; font-weight:800; letter-spacing:.12em;
        text-transform:uppercase; color:var(--slate-2); }
      .brief h3{ margin:.34rem 0 .6rem; font-size:1.34rem; font-weight:700;
        letter-spacing:-.012em; color:#0E2A45; }
      .brief .brief-actions{ display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
      .brief .chip{ display:inline-flex; align-items:center; gap:6px;
        background:#fff; border:1px solid #D3E2F1; border-radius:999px;
        padding:6px 13px; font-size:.82rem; font-weight:550; color:#22354A;
        text-decoration:none; cursor:pointer;
        box-shadow:var(--shadow-sm); animation:ssPop .5s var(--spring) both;
        transition:border-color .16s var(--ease), background .16s var(--ease),
                   transform .16s var(--ease), box-shadow .16s var(--ease); }
      .brief .chip:hover{ border-color:#9FC0E4; background:#EFF6FE;
        transform:translateY(-2px); box-shadow:var(--shadow-md); color:var(--accent); }
      .brief .chip:active{ transform:translateY(0); box-shadow:var(--shadow-sm); }
      .brief .chip b{ color:var(--accent); }
      .brief .chip .chip-go{ font-size:1.05rem; line-height:1; color:#9FB4CC;
        margin-left:1px; transition:transform .16s var(--ease), color .16s var(--ease); }
      .brief .chip:hover .chip-go{ transform:translateX(3px); color:var(--accent); }

      /* personalized strategy panel — ranked, reasoned plays per login */
      .strat{ position:relative; margin:0 0 30px; border-radius:16px;
        border:1px solid var(--slate-line); padding:20px 22px 12px;
        background:linear-gradient(135deg, #FAFBFC 0%, #F2F4F7 60%, #EDF1F6 100%);
        box-shadow:var(--shadow-sm); animation:ssFadeUp .6s var(--ease) both; }
      .strat::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
        border-radius:16px 0 0 16px;
        background:linear-gradient(var(--slate-2), var(--accent)); }
      .strat-head{ margin-bottom:14px; }
      .strat-head .eyebrow{ display:flex; align-items:center; gap:8px;
        font-size:.72rem; font-weight:800; letter-spacing:.12em;
        text-transform:uppercase; color:var(--slate-2); }
      .strat-head h3{ margin:.4rem 0 .5rem; font-size:1.24rem; font-weight:700;
        letter-spacing:-.012em; color:#0E2A45; line-height:1.35; }
      .strat-learn{ text-transform:none; letter-spacing:.02em; font-weight:700;
        font-size:.66rem; color:var(--accent); background:var(--accent-soft);
        border:1px solid #CFE0F0; border-radius:999px; padding:2px 9px; }
      .strat-co{ font-size:.78rem; color:var(--slate-2); line-height:1.5;
        border-top:1px dashed var(--slate-line); padding-top:10px; margin-top:2px; }
      .strat-play{ display:flex; gap:14px; padding:14px 2px;
        border-top:1px solid var(--slate-soft);
        animation:ssFadeUp .5s var(--ease) both; }
      .strat-play.strat-lead{ padding:16px 14px; margin:2px 0 4px;
        border-radius:12px; border:1px solid #CFE0F0;
        background:linear-gradient(120deg, #F3F8FD, #EAF2FB); }
      .strat-rank{ flex:0 0 auto; width:26px; height:26px; border-radius:8px;
        display:flex; align-items:center; justify-content:center;
        font-size:.86rem; font-weight:800; color:var(--slate-2);
        background:#fff; border:1px solid var(--slate-line); }
      .strat-lead .strat-rank{ color:#fff; border:none;
        background:linear-gradient(135deg, var(--accent), var(--accent-2)); }
      .strat-body{ flex:1 1 auto; min-width:0; }
      .strat-title{ display:flex; flex-wrap:wrap; align-items:center; gap:10px;
        font-size:.98rem; font-weight:700; color:#12283F; }
      .strat-impact{ font-size:.7rem; font-weight:800; letter-spacing:.02em;
        color:var(--slate-2); background:var(--slate-soft);
        border:1px solid var(--slate-line); border-radius:999px; padding:2px 9px; }
      .strat-lead .strat-impact{ color:var(--accent); background:var(--accent-soft);
        border-color:#CFE0F0; }
      .strat-thesis{ margin:.4rem 0 .5rem; font-size:.86rem; line-height:1.55;
        color:#37485C; }
      .strat-acts{ margin:0; padding-left:1.05rem; }
      .strat-acts li{ font-size:.82rem; line-height:1.5; color:#4A5A6D;
        margin:2px 0; }
      @media (max-width:680px){
        .strat{ padding:16px; } .strat-head h3{ font-size:1.06rem; }
      }

      /* roadmap phases with a connecting flow spine */
      .phase{ position:relative; padding:2px 0 20px 30px; }
      .phase::before{ content:""; position:absolute; left:9px; top:6px;
        width:12px; height:12px; border-radius:50%; background:var(--accent);
        box-shadow:0 0 0 4px var(--accent-soft); z-index:1; }
      .phase::after{ content:""; position:absolute; left:14px; top:14px; bottom:-6px;
        width:2px; background:linear-gradient(var(--accent), #C9D9EA); }
      .phase:last-child::after{ display:none; }
      .phase .card{ margin:0; }
      .phase .ph-tag{ font-size:.7rem; font-weight:700; letter-spacing:.08em;
        text-transform:uppercase; color:var(--slate-2); }

      /* user-guide numbered steps */
      .step{ display:flex; gap:14px; align-items:flex-start; margin-bottom:14px;
        animation:ssFadeUp .5s var(--ease) both; }
      .step .num{ flex:0 0 30px; width:30px; height:30px; border-radius:50%;
        display:flex; align-items:center; justify-content:center;
        font-family:var(--display); font-weight:700; font-size:.95rem; color:#fff;
        background:linear-gradient(145deg, var(--accent-2), var(--accent));
        box-shadow:var(--shadow-sm); }
      .step .step-body{ padding-top:2px; }
      .step .step-body b{ font-size:1rem; }
      .step .step-body div{ color:var(--muted); font-size:.92rem; margin-top:1px; }

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


class _Raw(str):
    """Marker: a table cell whose contents are already safe HTML (e.g. a pill)."""


def _pill(text, kind="neutral", dot=False):
    d = "<span class='pdot'></span>" if dot else ""
    return _Raw(f"<span class='pill pill-{kind}'>{d}{_esc(text)}</span>")


_RISK_KIND = {"high": "danger", "medium": "warn", "low": "ok"}


def _risk_pill(risk):
    return _pill(str(risk).title(), _RISK_KIND.get(risk, "neutral"), dot=True)


def _crit_pill_tbl(crit):
    kind = {"critical": "danger", "essential": "warn",
            "non-critical": "info"}.get(crit, "neutral")
    return _pill(crit, kind)


def _table(headers, rows, num_cols=()):
    """Render a premium read-only HTML table (sticky header, zebra, hover).

    `rows` is a list of cell sequences; a cell that is a _Raw is emitted as-is
    (for pills), everything else is HTML-escaped. `num_cols` = column indices to
    right-align with tabular figures."""
    num = set(num_cols)
    head = "".join(
        f"<th class='num'>{_esc(h)}</th>" if i in num else f"<th>{_esc(h)}</th>"
        for i, h in enumerate(headers))
    body = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            cell = c if isinstance(c, _Raw) else _esc(c)
            tds.append(f"<td class='num'>{cell}</td>" if i in num
                       else f"<td>{cell}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    st.markdown(
        f"<div class='ptable-wrap'><table class='ptable'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
        f"</table></div>", unsafe_allow_html=True)


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
        "<div class='brand-wrap'><div class='brand-name'>AISync"
        "<span class='tm'>&trade;</span></div>"
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
    "guide": "User Guide",
}

with st.sidebar:
    st.markdown(
        f"<div class='nav-head'>Plant</div>"
        f"<div style='font-weight:600;margin-bottom:.5rem'>"
        f"{_esc(st.session_state.get('plant_name',''))}</div>",
        unsafe_allow_html=True)
    st.markdown("<div class='nav-head'>Menu</div>", unsafe_allow_html=True)
    # Action-plan chips deep-link here via ?goto=<navkey>; honor it once, then
    # drop the param so a refresh doesn't keep forcing the same page.
    _goto = st.query_params.get("goto")
    if _goto in NAV and st.session_state.get("nav") != _goto:
        st.session_state["nav"] = _goto
    if _goto is not None:
        st.query_params.pop("goto", None)
    page = st.radio(" ", list(NAV.keys()), format_func=lambda k: NAV[k],
                    label_visibility="collapsed", key="nav")

    if st.session_state.get("_last_page") != page:
        db.log_event("pageview", uid=st.session_state.get("uid"),
                     visitor=_visitor_id(), detail=NAV[page])
        # Teach this login's AI persona what they focus on (page = a topic key).
        user_profile.log_signal(page)
        st.session_state["_last_page"] = page
    st.divider()
    if st.button("Load HPL demo data", use_container_width=True,
                 type="primary", key="btn_load_demo"):
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
        if st.button("Reset workspace", use_container_width=True,
                     key="btn_reset_ws"):
            st.session_state["confirm_reset"] = True; st.rerun()

    st.divider()
    # Per-login AI persona: sets whose priorities the strategist leads with.
    _role_keys = list(user_profile.ROLES.keys())
    _cur_role = user_profile.get_role()
    st.markdown("<div class='nav-head'>Your role</div>", unsafe_allow_html=True)
    _picked_role = st.selectbox(
        " ", _role_keys, index=_role_keys.index(_cur_role),
        format_func=lambda r: user_profile.ROLES[r]["label"],
        label_visibility="collapsed", key="role_select")
    if _picked_role != _cur_role:
        user_profile.set_role(_picked_role)
        st.rerun()
    st.caption(user_profile.ROLES[_picked_role]["blurb"])

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
    "<div class='brand-wrap'><div class='brand-name'>AISync"
    "<span class='tm'>&trade;</span></div>"
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

    # Personalized manager action band — computed for THIS plant.
    brief = spares.manager_brief(rows)
    plant = st.session_state.get("plant_name", "your plant")
    # each action deep-links to the page that lets the manager act on it
    _CHIP_NAV = {
        "Clear obsolete stock": "obs",
        "Trim excess to AI-optimal": "opt",
        "Reorder critical spares FIRST": "opt",
        "Plan replenishment": "opt",
        "Investigate rising consumption": "pdm",
    }
    # a chip is a full-page link, so carry the session token forward (the app
    # keeps ?s= in the URL to survive reloads) or the click would log you out.
    _tok = st.query_params.get("s")
    _spref = f"s={_tok}&amp;" if _tok else ""
    chips = "".join(
        f"<a class='chip' href='?{_spref}goto={_CHIP_NAV.get(label, 'dash')}' "
        f"target='_self'>{_esc(label)} · <b>{_esc(val)}</b>"
        f"<span class='chip-go'>&rsaquo;</span></a>"
        for label, val in brief["actions"])
    st.markdown(
        f"<div class='brief'><div class='eyebrow'>AISync · action plan for "
        f"{_esc(plant)}</div><h3>{_esc(brief['headline'])}</h3>"
        f"<div class='brief-actions'>{chips}</div></div>",
        unsafe_allow_html=True)

    # ---- personalized strategy: the strategist reasons over this plant's
    # numbers and ranks the plays for whoever is logged in (role + learning).
    persona = user_profile.persona()
    plan = strategist.briefing(rows, persona)
    _learn = ("<span class='strat-learn'>learning your focus</span>"
              if persona["learned"] else "")
    play_html = ""
    for i, pl in enumerate(plan["plays"][:4]):
        fit = " strat-lead" if i == 0 else ""
        acts = "".join(f"<li>{_esc(a)}</li>" for a in pl["actions"])
        play_html += (
            f"<div class='strat-play{fit}'>"
            f"<div class='strat-rank'>{i+1}</div>"
            f"<div class='strat-body'><div class='strat-title'>{_esc(pl['title'])}"
            f"<span class='strat-impact'>{_esc(spares.cr(pl['impact']))} impact</span>"
            f"</div><div class='strat-thesis'>{_esc(pl['thesis'])}</div>"
            f"<ul class='strat-acts'>{acts}</ul></div></div>")
    st.markdown(
        f"<div class='strat'><div class='strat-head'>"
        f"<div class='eyebrow'>Strategy · tuned for {_esc(persona['label'])}{_learn}</div>"
        f"<h3>{_esc(plan['headline'])}</h3>"
        f"<div class='strat-co'>{_esc(plan['company'])}</div></div>"
        f"{play_html}</div>", unsafe_allow_html=True)

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

    def _status_cell(r):
        if r["obsolete"]:
            return _pill("Obsolete", "danger", dot=True)
        if r.get("insurance"):
            return _pill("Insurance", "info", dot=True)
        if r["excess_value"] > 0:
            return _pill(f"Excess {spares.cr(r['excess_value'])}", "warn", dot=True)
        return _pill("Optimal", "ok", dot=True)

    _table(
        ["Spare", "Equipment", "Criticality", "On hand", "Capital", "Status"],
        [[r["name"] or r["sku"], r.get("equipment", ""),
          _crit_pill_tbl(r.get("criticality", "")), int(r["on_hand"]),
          spares.cr(r["capital"]), _status_cell(r)] for r in top],
        num_cols=(3, 4))


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
    _table(
        ["Spare", "Equipment", "Criticality", "On hand", "Years idle",
         "Locked capital"],
        [[r["name"] or r["sku"], r.get("equipment", ""),
          _crit_pill_tbl(r.get("criticality", "")), int(r["on_hand"]),
          (f"{r['age_years']:.1f}" if r.get("age_years") else "—"),
          spares.cr(r["capital"])] for r in obs],
        num_cols=(3, 4, 5))

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
    chart = (alt.Chart(wk_df)
             .mark_bar(color="#1F4E79", cornerRadiusTopLeft=6,
                       cornerRadiusTopRight=6, size=34)
             .encode(x=alt.X("Day:N", sort=dows, title=None,
                             axis=alt.Axis(labelColor="#6E6E73",
                                           labelFont="Inter", labelPadding=8)),
                     y=alt.Y("Predicted units:Q", title=None,
                             axis=alt.Axis(labelColor="#AEAEB2",
                                           tickCount=4, gridColor="#EDEDF0")))
             .properties(height=240)
             .configure_axis(domainColor="#E6E6EB", domainWidth=1,
                             tickColor="#E6E6EB", grid=False)
             .configure_view(strokeWidth=0))
    st.altair_chart(chart, use_container_width=True)

    st.subheader("Per-spare AI read")
    _table(
        ["Spare", "Equipment", "Forecast/day", "Trend/mo", "Momentum", "Peak day"],
        [[r["name"] or r["sku"], r.get("equipment", ""),
          f"{r['forecast']['daily_rate']:.3f}",
          f"{r['forecast']['ai_analysis']['trend_pct_month']:+.0f}%",
          f"{r['forecast']['ai_analysis']['momentum_pct']:+.0f}%",
          r["forecast"]["ai_analysis"]["busiest_day"]] for r in ai_rows],
        num_cols=(2, 3, 4))


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
            _table(
                ["Spare", "Equipment", "Criticality", "Type", "Risk",
                 "On hand", "Order qty", "Value"],
                [[r["name"] or r["sku"], r.get("equipment", ""),
                  _crit_pill_tbl(r.get("criticality", "")),
                  _pill("Insurance", "info") if r.get("insurance")
                  else _pill("Demand", "neutral"),
                  _risk_pill(r["risk"]), int(r["on_hand"]),
                  int(r["reco_qty"]), spares.cr(r["reco_qty"] * r["unit_cost"])]
                 for r in lst],
                num_cols=(5, 6, 7))

        st.markdown("##### Fund these now")
        _reo_table(chosen)
        if deferred:
            st.markdown("##### Deferred to next cycle (raise budget to include)")
            _reo_table(deferred)

    ins = [r for r in rows if r.get("insurance")]
    if ins:
        st.subheader("Insurance spares (strategic minimum)")
        st.caption("Ultra-expensive critical units (≥ ₹1 Cr each) are held to a "
                   "strategic minimum of "
                   f"{spares.INSURANCE_MIN} per train — never demand-forecast, "
                   "never flagged excess. One failure must not idle the train.")
        _table(
            ["Spare", "Equipment", "On hand", "Strategic min", "Risk",
             "Unit cost"],
            [[r["name"] or r["sku"], r.get("equipment", ""), int(r["on_hand"]),
              spares.INSURANCE_MIN, _risk_pill(r["risk"]),
              spares.cr(r["unit_cost"])] for r in ins],
            num_cols=(2, 3, 5))


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
    up = st.file_uploader(
        "Upload SAP / Excel / CSV / PDF export",
        type=["xlsx", "xls", "csv", "pdf"], key="inv_upload",
        help="Stock counts and issue history from Excel, CSV, or a tabular PDF "
             "report (e.g. an SAP MB52 stock dump). Columns are auto-mapped.")
    file_tag = (up.name, up.size) if up is not None else None
    already = st.session_state.get("imported_file") == file_tag
    if up is None or already:
        return
    st.markdown("#### Reading your export")
    ad = TabularAdapter()
    try:
        df = ad.read(up)
    except RuntimeError as e:
        st.error(str(e))
        return
    if df is None or df.empty:
        st.error("That file had no readable rows. Try an Excel/CSV export.")
        return
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
         "Upload file (Excel · CSV · PDF)", "Add a spare"])

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
# question keyword -> persona learning theme (see profile.TOPIC_DIMENSION).
# Ordered so the more specific signal wins; first hit in the question is logged.
_ASK_THEMES = {
    "capital": "capital", "release": "capital", "cash": "capital",
    "obsolete": "obsolete", "dead": "obsolete", "scrap": "obsolete",
    "excess": "excess",
    "reorder": "reorder", "buy": "reorder", "order": "reorder",
    "forecast": "forecast", "consumption": "forecast", "demand": "forecast",
    "maintenance": "maintenance", "failure": "maintenance", "fail": "maintenance",
    "shutdown": "shutdown", "trip": "shutdown",
    "risk": "risk", "critical": "risk",
}


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
        "What will maintenance cost this month?",
        "How much can we release?",
        "What should we reorder first?",
        "Which equipment is heading to failure?",
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
        # teach the persona what this user asks about (question theme -> focus)
        user_profile.log_signal("ask")
        for _theme in _ASK_THEMES:
            if _theme in question.lower():
                user_profile.log_signal(_theme)
                break
        hist.append((question, ans))

    if hist and st.button("Clear chat", key="ask_clear"):
        st.session_state["ask_history"] = []
        st.rerun()

    def _md(txt):
        return (txt or "").replace("~", "\\~")

    for uq, ua in hist:
        with st.chat_message("user", avatar="👷"):
            st.markdown(_md(uq))
        with st.chat_message("assistant", avatar="🔧"):
            st.markdown(_md(ua))


# ============================================================ PAGE: ROADMAP
def page_roadmap():
    st.subheader("Implementation roadmap")
    plant = st.session_state.get("plant_name", "your plant")

    if not have_data:
        st.caption("A phased, SAP-integrated rollout — start read-only on a "
                   "data export, earn trust, then close the loop with "
                   "procurement. Load your spare master and this plan "
                   "personalizes to your plant's own numbers.")
        _need_data_hint()
        return

    rows = _load_rows()
    plan = spares.plant_plan(rows, plant_name=plant)
    st.caption(f"Generated for **{plant}** from its own data — the phases are "
               "ordered so the highest-value lever for this plant comes first. "
               "Every figure is computed, never assumed.")

    for ph in plan["phases"]:
        st.markdown(
            f"<div class='phase'><div class='card'>"
            f"<div class='ph-tag'>{_esc(ph['tag'])}</div>"
            f"<h4>{_esc(ph['title'])}</h4>"
            f"<div style='color:#5B6879;font-size:.92rem'>{_esc(ph['body'])}</div>"
            f"</div></div>",
            unsafe_allow_html=True)

    st.subheader("Why AISync")
    cc = st.columns(3)
    facts = [
        ("Every number is auditable",
         "Each figure traces to the plant's own issues and stock — you can point "
         "to the line item behind it. Nothing is estimated or invented."),
        ("Runs on your infrastructure",
         "The forecasting model is self-contained and needs no external service "
         "or paid API, so plant data never leaves your environment."),
        ("Reliability comes first",
         "Critical and insurance spares are protected to tighter service levels. "
         "Capital is released only from obsolete and genuinely excess stock — "
         "never at the cost of an unplanned shutdown."),
    ]
    for i, (h, b) in enumerate(facts):
        cc[i].markdown(
            f"<div class='card'><h4>{_esc(h)}</h4>"
            f"<div style='color:#5B6879;font-size:.9rem'>{_esc(b)}</div></div>",
            unsafe_allow_html=True)


# ============================================================ PAGE: USER GUIDE
def page_guide():
    st.subheader("User guide — how to use AISync")
    st.caption("Plain and simple. If you manage the plant's spares, this is all "
               "you need to know. No jargon, no training required.")

    st.markdown("#### What AISync does for you")
    st.markdown(
        "<div class='card'>AISync looks at the spare parts you keep in stock "
        "and the money tied up in them. It tells you three things: "
        "<b>which spares are dead money</b> you can free up, "
        "<b>which spares to reorder</b> before they cause a breakdown, and "
        "<b>which equipment may be about to fail</b> — all from your own "
        "records. It never guesses a number.</div>",
        unsafe_allow_html=True)

    st.markdown("#### Get started in 3 steps")
    steps = [
        ("Load your spares",
         "Go to <b>Spare Master &amp; Data</b> in the sidebar. Upload your SAP "
         "or Excel export — AISync reads messy files and matches the columns "
         "for you. In a hurry? Click <b>Load HPL demo data</b> to see it work."),
        ("Read your action plan",
         "Open the <b>Executive Dashboard</b>. The blue band at the top is your "
         "to-do list for the week, written in rupees: how much you can free up "
         "and what to reorder first."),
        ("Take the actions",
         "Use <b>Obsolete Detection</b> to clear dead stock, <b>Criticality "
         "Optimizer</b> to see what to buy, and <b>Predictive Maintenance</b> "
         "to catch failures early. That's it."),
    ]
    for i, (title, body) in enumerate(steps, 1):
        st.markdown(
            f"<div class='step'><div class='num'>{i}</div>"
            f"<div class='step-body'><b>{title}</b><div>{body}</div></div></div>",
            unsafe_allow_html=True)

    st.markdown("#### What each page tells you")
    guide = [
        ("Executive Dashboard", "Your money at a glance — how much capital is "
         "blocked, how much you can safely release, and the week's action plan."),
        ("Obsolete Detection", "Spares that haven't moved in over 5 years — dead "
         "money you can redeploy, sell, or write off."),
        ("Consumption Forecast", "How fast each spare gets used, and which are "
         "speeding up or slowing down — learned by the AI from your history."),
        ("Criticality Optimizer", "What to reorder, most important first, and how "
         "far a limited budget will stretch. Critical spares are never cut."),
        ("Predictive Maintenance", "Spares being used faster than normal — an "
         "early warning that a machine may be heading for failure."),
        ("Spare Master & Data", "Where you record issues and receipts, set stock "
         "counts, or upload a fresh SAP export."),
        ("Ask AISync", "Type a plain question ('how much can we release?') and get "
         "an answer straight from your numbers."),
        ("Implementation Roadmap", "Your step-by-step rollout plan, built from "
         "your plant's own data."),
    ]
    for name, what in guide:
        st.markdown(
            f"<div class='card' style='margin-bottom:8px'><b>{_esc(name)}</b>"
            f"<div style='color:#5B6879;font-size:.92rem;margin-top:2px'>"
            f"{_esc(what)}</div></div>",
            unsafe_allow_html=True)

    st.markdown("#### Good to know")
    st.markdown(
        "- **Your data is private.** Each plant workspace only ever sees its "
        "own spares — no one else's.\n"
        "- **Nothing is invented.** Every rupee figure is calculated from the "
        "issues and stock you loaded.\n"
        "- **Critical spares are protected.** AISync only ever suggests "
        "releasing obsolete or genuinely excess stock — never the spares that "
        "keep the plant running.\n"
        "- **Stuck?** Use **Ask AISync** and just type your question.")


# ============================================================ DISPATCH
PAGES = {
    "dash": page_dashboard, "obs": page_obsolete, "fcast": page_forecast,
    "opt": page_optimize, "pdm": page_predictive, "master": page_master,
    "ask": page_ask, "road": page_roadmap, "guide": page_guide,
}
PAGES[page]()
