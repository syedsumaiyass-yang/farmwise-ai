import sys
import os
import uuid
from datetime import datetime

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)

import streamlit as st
import requests

import plotly.io as pio

# Falls back to localhost for local development. When deployed, set a
# BACKEND_URL secret/env var pointing at your hosted FastAPI backend
# (e.g. "https://your-backend.onrender.com/chat") - a deployed Streamlit
# app has no way to reach "127.0.0.1" since that just means "this same
# container", not your machine.
def _get_backend_url():
    try:
        return st.secrets["BACKEND_URL"]
    except Exception:
        # No secrets.toml locally (normal for local dev) - fall back
        # to an env var, then to localhost.
        return os.getenv("BACKEND_URL", "http://127.0.0.1:8000/chat")


BACKEND_URL = _get_backend_url()

# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="FarmWise AI Assistant",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================================
# THEME / CSS
# ==========================================================
# Fresh, friendly "agri-dashboard" identity inspired by the
# provided mockup: light mint/white surfaces, a green->emerald
# accent, soft rounded cards with light shadows, and colorful
# icon chips instead of the previous flat minimal look.
#
# Palette:
#   Ink         #1F2A24  (primary text)
#   Mute        #667B70  (secondary text)
#   Faint       #9AAAA1  (tertiary / placeholder text)
#   Line        #E4EEE7  (hairline dividers, borders)
#   Surface     #F3FAF5  (light mint panels - sidebar bg)
#   White       #FFFFFF  (page / card background)
#   Accent      #1FA24A  (primary green)
#   Accent-Dk   #16803A  (darker green - gradients / hover)
#   Accent-Bg   #E9F9EF  (accent tint - selected / hover states)
#   Accent-Bg2  #DFF5E6  (slightly deeper tint - icon chips)
#
# Type: "Inter" throughout.
# ==========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    :root {
        --ink: #1F2A24;
        --mute: #667B70;
        --faint: #9AAAA1;
        --line: #E4EEE7;
        --surface: #F3FAF5;
        --white: #FFFFFF;
        --accent: #1FA24A;
        --accent-dk: #16803A;
        --accent-bg: #E9F9EF;
        --accent-bg2: #DFF5E6;
        --amber: #F59E0B;
        --amber-bg: #FEF3DA;
        --blue: #3B82F6;
        --blue-bg: #E4EEFE;
        --red: #EF4444;
    }

    /* ---------- Hide Streamlit chrome ---------- */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; height: 0; }
    [data-testid="stDeployButton"] { display: none; }
    div[data-testid="stDecoration"] { display: none; }

    /* ---------- App background ---------- */
    .stApp {
        background: var(--white);
    }

    div.block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        max-width: 1180px;
    }

    /* ==========================================================
       SIDEBAR TOGGLE
       This is Streamlit's OWN built-in collapse/expand control -
       we don't replace or hide it (that caused more problems than
       it solved). We just re-skin it so it's clearly visible
       against our white/mint background instead of the default
       faint gray icon. Covers both the icon Streamlit shows when
       the sidebar is open (inside its header) and the floating
       one it shows when collapsed - different internal names
       across Streamlit versions, so both are targeted.
       ========================================================== */
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarHeader"] button,
    header[data-testid="stHeader"] button {
        background: var(--accent-bg2) !important;
        border-radius: 8px !important;
        opacity: 1 !important;
        position: relative !important;
        z-index: 999999 !important;
        visibility: visible !important;
        pointer-events: auto !important;
    }
    [data-testid="collapsedControl"] svg,
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="stSidebarHeader"] svg,
    header[data-testid="stHeader"] svg {
        fill: var(--accent-dk) !important;
        color: var(--accent-dk) !important;
    }
    [data-testid="stSidebarHeader"] {
        min-height: 2.75rem !important;
        z-index: 999999 !important;
        position: relative !important;
    }

    /* ==========================================================
       SIDEBAR
       ========================================================== */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--surface) 0%, #EEF8F1 100%);
        border-right: 1px solid var(--line);
    }
    section[data-testid="stSidebar"] * {
        color: var(--ink);
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 2.75rem;
    }

    .fw-logo-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 4px 2px 2px 2px;
    }
    .fw-logo-icon {
        font-size: 1.25rem;
        width: 40px;
        height: 40px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, var(--accent-bg2), var(--accent-bg));
        border: 1px solid var(--line);
        flex-shrink: 0;
    }
    .fw-logo {
        font-size: 1.05rem;
        font-weight: 800;
        color: var(--ink);
        line-height: 1.2;
    }
    .fw-logo-sub {
        color: var(--mute);
        font-size: 0.7rem;
        margin-top: 1px;
        font-weight: 500;
    }

    .fw-sidebar-label {
        font-size: 0.68rem;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        color: var(--faint);
        font-weight: 800;
        margin: 18px 0 8px 3px;
        display: flex;
        align-items: center;
        gap: 5px;
    }

    /* New chat button — solid green gradient, pill-ish */
    section[data-testid="stSidebar"] .stButton>button {
        background: linear-gradient(135deg, var(--accent), var(--accent-dk));
        color: #FFFFFF !important;
        border: none;
        font-weight: 700;
        border-radius: 10px;
        padding: 0.6rem 0.8rem;
        transition: all 0.15s ease;
        box-shadow: 0 4px 10px rgba(31, 162, 74, 0.25);
    }
    section[data-testid="stSidebar"] .stButton>button:hover {
        filter: brightness(1.06);
        box-shadow: 0 6px 14px rgba(31, 162, 74, 0.32);
        transform: translateY(-1px);
    }
    section[data-testid="stSidebar"] .stButton>button p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }

    /* Chat history rows — override the gradient button style above */
    .fw-history-row .stButton>button,
    .fw-history-row-active .stButton>button {
        background: transparent !important;
        color: var(--mute) !important;
        border: 1px solid transparent !important;
        text-align: left !important;
        font-weight: 500 !important;
        padding: 0.5rem 0.65rem !important;
        border-radius: 9px !important;
        width: 100%;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        box-shadow: none !important;
        transition: all 0.12s ease;
    }
    .fw-history-row .stButton>button p,
    .fw-history-row-active .stButton>button p {
        color: inherit !important;
        font-weight: inherit !important;
    }
    .fw-history-row .stButton>button:hover {
        background: var(--white) !important;
        color: var(--ink) !important;
        border-color: var(--line) !important;
    }
    .fw-history-row-active .stButton>button {
        background: var(--accent-bg) !important;
        color: var(--accent-dk) !important;
        font-weight: 700 !important;
        border-color: var(--accent-bg2) !important;
    }
    .fw-del-btn .stButton>button {
        background: transparent !important;
        color: var(--faint) !important;
        border: none !important;
        padding: 0.3rem !important;
        font-size: 0.8rem !important;
        box-shadow: none !important;
        border-radius: 6px !important;
    }
    .fw-del-btn .stButton>button:hover {
        color: var(--red) !important;
        background: transparent !important;
        box-shadow: none !important;
        transform: none !important;
    }

    section[data-testid="stSidebar"] hr {
        border-color: var(--line);
        margin: 14px 0;
    }

    section[data-testid="stSidebar"] .streamlit-expanderHeader {
        background: var(--white);
        border: 1px solid var(--line);
        border-radius: 9px;
        font-weight: 600;
        font-size: 0.82rem;
        color: var(--mute) !important;
    }
    section[data-testid="stSidebar"] .streamlit-expanderContent {
        background: transparent;
    }

    /* Explore list */
    .fw-explore-item {
        display: flex;
        align-items: center;
        gap: 9px;
        padding: 7px 8px;
        border-radius: 8px;
        font-size: 0.86rem;
        font-weight: 550;
        color: var(--mute);
        margin-bottom: 1px;
    }
    .fw-explore-item span.fw-explore-ico {
        font-size: 0.95rem;
    }

    .fw-footer-caption {
        color: var(--faint) !important;
        font-size: 0.68rem;
    }
    .fw-footer-row {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 10px;
    }

    /* ==========================================================
       MAIN HEADER
       ========================================================== */
    .fw-main-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 18px;
    }
    .fw-main-title-row {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .fw-main-title-icon {
        font-size: 1.7rem;
        width: 46px;
        height: 46px;
        border-radius: 13px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--accent-bg2);
    }
    .fw-main-title h1 {
        font-size: 1.6rem;
        font-weight: 800;
        margin: 0;
        line-height: 1.15;
        color: var(--ink);
    }
    .fw-main-title h1 span {
        color: var(--accent);
    }
    .fw-main-title p {
        margin: 2px 0 0 0;
        color: var(--mute);
        font-size: 0.88rem;
    }
    .fw-header-icons {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .fw-header-icon-btn {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: var(--white);
        border: 1px solid var(--line);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
    .fw-header-avatar {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: var(--accent-bg2);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
        border: 1px solid var(--accent-bg2);
    }

    /* ==========================================================
       HERO BANNER
       ========================================================== */
    .fw-hero {
        position: relative;
        background: linear-gradient(120deg, var(--accent-bg) 0%, #F4FBF6 55%, #FBFDFB 100%);
        border: 1px solid var(--accent-bg2);
        border-radius: 20px;
        padding: 26px 30px;
        margin-bottom: 26px;
        overflow: hidden;
        min-height: 108px;
        display: flex;
        align-items: center;
    }
    .fw-hero-inner {
        display: flex;
        align-items: center;
        gap: 16px;
        z-index: 2;
        max-width: 62%;
    }
    .fw-hero-icon {
        width: 46px;
        height: 46px;
        border-radius: 50%;
        background: rgba(255,255,255,0.75);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .fw-hero-text {
        font-size: 1.02rem;
        font-weight: 650;
        color: var(--ink);
        line-height: 1.45;
    }
    .fw-hero-deco {
        position: absolute;
        right: 26px;
        bottom: 0;
        font-size: 4.5rem;
        line-height: 1;
        opacity: 0.95;
        z-index: 1;
        filter: drop-shadow(0 6px 10px rgba(0,0,0,0.06));
    }
    .fw-hero-sun {
        position: absolute;
        top: 18px;
        right: 90px;
        font-size: 1.7rem;
        opacity: 0.9;
    }

    /* ==========================================================
       SECTION LABELS
       ========================================================== */
    .fw-section-label {
        font-size: 1rem;
        font-weight: 800;
        color: var(--ink);
        margin: 4px 0 12px 0;
        display: flex;
        align-items: center;
        gap: 7px;
    }

    /* ==========================================================
       QUICK ACTION CARDS
       ========================================================== */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] .fw-qa-marker) {
        border: 1px solid var(--line) !important;
        border-radius: 16px !important;
        background: var(--white) !important;
        box-shadow: 0 2px 10px rgba(20, 40, 30, 0.04) !important;
        padding: 4px !important;
        transition: all 0.15s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] .fw-qa-marker):hover {
        border-color: var(--accent-bg2) !important;
        box-shadow: 0 6px 16px rgba(20, 40, 30, 0.08) !important;
        transform: translateY(-2px);
    }
    .fw-qa-icon {
        width: 42px;
        height: 42px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.15rem;
        margin-bottom: 10px;
    }
    .fw-qa-icon.g { background: var(--accent-bg2); }
    .fw-qa-icon.b { background: var(--blue-bg); }
    .fw-qa-icon.a { background: var(--amber-bg); }
    .fw-qa-title {
        font-weight: 750;
        font-size: 0.95rem;
        color: var(--ink);
        margin-bottom: 2px;
    }
    .fw-qa-sub {
        font-size: 0.78rem;
        color: var(--mute);
        margin-bottom: 10px;
    }
    .fw-qa-wrap .stButton>button {
        background: var(--surface) !important;
        color: var(--accent-dk) !important;
        border: 1px solid var(--accent-bg2) !important;
        border-radius: 9px !important;
        font-weight: 650 !important;
        font-size: 0.8rem !important;
        padding: 0.42rem 0.7rem !important;
        box-shadow: none !important;
        width: 100%;
        transition: all 0.12s ease;
    }
    .fw-qa-wrap .stButton>button:hover {
        background: var(--accent) !important;
        color: #FFFFFF !important;
        border-color: var(--accent) !important;
    }
    .fw-qa-wrap .stButton>button p { color: inherit !important; }

    /* ==========================================================
       CHAT BUBBLES
       ========================================================== */
    div[data-testid="stChatMessage"] {
        max-width: 78%;
        margin-bottom: 14px;
        padding: 12px 16px;
        border-radius: 16px;
        border: none;
        background: transparent;
        box-shadow: none;
    }

    div[data-testid="stChatMessage"]:not(:has(div[data-testid="stChatMessageAvatarUser"])) {
        margin-right: auto;
        margin-left: 0;
        padding-left: 4px;
        background: var(--white);
    }

    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
        margin-left: auto;
        margin-right: 0;
        flex-direction: row-reverse;
        background: var(--accent-bg);
        border: 1px solid var(--accent-bg2);
        gap: 8px;
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) p,
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) span,
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) div {
        color: var(--ink) !important;
        font-weight: 480;
    }

    /* ==========================================================
       ANALYTICS CONTENT (charts + metrics)
       ========================================================== */
    div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlockBorderWrapper"]:not(:has(.fw-qa-marker)) {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 6px 0 4px 0 !important;
    }

    div[data-testid="stMetric"] {
        background: var(--accent-bg);
        border: 1px solid var(--accent-bg2);
        border-radius: 12px;
        padding: 10px 14px;
    }

    /* ==========================================================
       METRIC + CHART CONTENT
       ========================================================== */
    .fw-metric-inner {
        padding: 6px 0 10px 0;
    }
    .fw-metric-label {
        font-size: 0.7rem;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        color: var(--mute);
        font-weight: 700;
        margin-bottom: 6px;
    }
    .fw-metric-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: var(--accent-dk);
        line-height: 1.1;
    }
    .fw-metric-value span {
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--mute);
        margin-left: 6px;
    }

    .fw-chart-inner {
        padding: 10px 12px 4px 12px;
        border: 1px solid var(--line);
        border-radius: 14px;
        margin-top: 4px;
        background: var(--white);
    }
    .fw-chart-title {
        font-weight: 650;
        font-size: 0.82rem;
        color: var(--mute);
        margin: 2px 0 4px 0;
    }

    /* ==========================================================
       CHAT INPUT
       Streamlit's own internal textarea/wrapper still carries its
       default border, focus outline, and default red accent color
       underneath whatever we style on the outer container - without
       stripping those explicitly, you get two borders stacked on
       top of each other (ours + Streamlit's native one showing
       through). Everything inside is neutralized here so only the
       outer pill is visible.
       ========================================================== */
    div[data-testid="stChatInput"] {
        border-radius: 999px !important;
        border: 1px solid var(--line) !important;
        box-shadow: 0 2px 10px rgba(20,40,30,0.05) !important;
        background: var(--white) !important;
        padding-left: 6px !important;
        overflow: hidden !important;
    }
    div[data-testid="stChatInput"]:focus-within {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-bg) !important;
    }
    div[data-testid="stChatInput"] > div,
    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] [data-baseweb] {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
        background: transparent !important;
        border-radius: 999px !important;
    }
    div[data-testid="stChatInput"] *:focus,
    div[data-testid="stChatInput"] *:focus-visible {
        outline: none !important;
        box-shadow: none !important;
        border-color: transparent !important;
    }
    div[data-testid="stChatInput"] textarea {
        font-size: 0.95rem !important;
    }
    button[data-testid="stChatInputSubmitButton"] {
        background: var(--accent) !important;
        border-radius: 50% !important;
        color: #FFFFFF !important;
    }
    button[data-testid="stChatInputSubmitButton"]:hover {
        background: var(--accent-dk) !important;
    }

    /* ==========================================================
       RESPONSIVENESS
       ========================================================== */
    @media (max-width: 780px) {
        div[data-testid="stChatMessage"] { max-width: 92%; }
        .fw-hero-inner { max-width: 100%; }
        .fw-hero-deco { display: none; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# "Quick Actions" cards at the top of the welcome screen - each
# just fires the same submit_question() flow as any other prompt,
# with a representative question for that category.
QUICK_ACTIONS = [
    ("📈", "g", "Crop Yield Trend", "View trends over time", "Show India's crop yield trend"),
    ("🌍", "b", "Compare Countries", "India vs other nations", "Compare India and China"),
    ("🏆", "a", "Top Crops", "Highest yielding crops", "Top crops by yield"),
    ("🌧", "b", "Rainfall Analysis", "Insights & patterns", "Rainfall vs Yield"),
]

CAPABILITIES = []  # unused - capability card grid removed for a shorter welcome screen

# ==========================================================
# SESSION STATE
# ==========================================================
# All state lives only in st.session_state, so a full browser
# reload starts a brand new Streamlit session and every chat
# created before is gone - nothing is written to disk.
# ==========================================================


def _new_chat(select=True):

    chat_id = str(uuid.uuid4())

    st.session_state.chats[chat_id] = {
        "title": "New chat",
        "created": datetime.now().strftime("%H:%M"),
        "messages": [],
    }

    if select:
        st.session_state.current_chat_id = chat_id

    return chat_id


if "chats" not in st.session_state:

    st.session_state.chats = {}
    st.session_state.current_chat_id = None

if not st.session_state.chats:

    _new_chat()

if (
    st.session_state.current_chat_id is None
    or st.session_state.current_chat_id not in st.session_state.chats
):
    st.session_state.current_chat_id = next(iter(st.session_state.chats))


current_chat = st.session_state.chats[st.session_state.current_chat_id]

# ==========================================================
# SIDEBAR
# ==========================================================

with st.sidebar:

    st.markdown(
        """
        <div class="fw-logo-row">
            <div class="fw-logo-icon">🌱</div>
            <div>
                <div class="fw-logo">FarmWise AI</div>
                <div class="fw-logo-sub">Agricultural Intelligence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    if st.button("➕  New Chat", use_container_width=True):
        _new_chat()
        st.rerun()

    st.markdown('<div class="fw-sidebar-label">💬 Conversations</div>', unsafe_allow_html=True)

    # Most recently created chats first
    ordered_ids = list(st.session_state.chats.keys())[::-1]

    for chat_id in ordered_ids:

        chat = st.session_state.chats[chat_id]
        is_active = chat_id == st.session_state.current_chat_id

        row_class = "fw-history-row-active" if is_active else "fw-history-row"

        col_select, col_delete = st.columns([0.85, 0.15])

        with col_select:
            st.markdown(f'<div class="{row_class}">', unsafe_allow_html=True)

            label = ("🟢 " if is_active else "💬 ") + chat["title"]

            if st.button(label, key=f"select_{chat_id}", use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        with col_delete:
            st.markdown('<div class="fw-del-btn">', unsafe_allow_html=True)

            if st.button("✕", key=f"delete_{chat_id}"):

                del st.session_state.chats[chat_id]

                if not st.session_state.chats:
                    _new_chat()
                elif chat_id == st.session_state.current_chat_id:
                    st.session_state.current_chat_id = next(
                        iter(st.session_state.chats)
                    )

                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    st.markdown('<div class="fw-sidebar-label">✨ Explore</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fw-explore-item"><span class="fw-explore-ico">📊</span> Data Insights</div>
        <div class="fw-explore-item"><span class="fw-explore-ico">🌱</span> Crop Guide</div>
        <div class="fw-explore-item"><span class="fw-explore-ico">⚙️</span> Settings</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="fw-footer-row">
            <span>🛡️</span>
            <div>
                <div class="fw-footer-caption" style="font-weight:700;">FarmWise AI v2.0</div>
                <div class="fw-footer-caption">Chats are session based</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ==========================================================
# ASK / SUBMIT HELPER
# ==========================================================
# Shared by the chat input box AND the clickable example chips,
# so both paths behave identically.
# ==========================================================


def submit_question(question):

    # Build the history payload BEFORE appending the new user message -
    # this is the full prior conversation (role/content only), which IS
    # the session memory. No server-side filter tracking needed - the
    # LLM reasons over this history itself on every turn.
    history_payload = [
        {
            "role": m["role"],
            "content": m["content"],
            "filters": m.get("applied_filters"),
        }
        for m in current_chat["messages"]
    ]

    current_chat["messages"].append(
        {
            "role": "user",
            "content": question
        }
    )

    # First user message in a chat becomes its sidebar title
    if current_chat["title"] == "New chat":
        current_chat["title"] = (
            question if len(question) <= 42 else question[:39] + "..."
        )

    with st.spinner("🌾 Thinking..."):

        try:

            response = requests.post(

                BACKEND_URL,

                json={
                    "question": question,
                    "history": history_payload,
                },

                timeout=120,  # Render free tier can be slow on cold start
            )

            response.raise_for_status()

            result = response.json()

            answer = result.get("answer")

            chart_json = result.get("chart_json")

            chart_summary = result.get("chart_summary")

            applied_filters = result.get("applied_filters")

        except requests.exceptions.Timeout:

            answer = (
                "❌ The backend took too long to respond (it may be "
                "waking up from sleep on Render's free tier — try again "
                "in ~30-60 seconds)."
            )

            chart_json = None
            chart_summary = None
            applied_filters = None

        except requests.exceptions.ConnectionError as exc:

            answer = f"❌ Couldn't reach the backend at {BACKEND_URL}. ({exc})"

            chart_json = None
            chart_summary = None
            applied_filters = None

        except requests.exceptions.HTTPError as exc:

            answer = (
                f"❌ Backend returned an error "
                f"({response.status_code}): {response.text[:300]}"
            )

            chart_json = None
            chart_summary = None
            applied_filters = None

        except Exception as exc:

            answer = f"❌ Unexpected error: {type(exc).__name__}: {exc}"

            chart_json = None

            chart_summary = None

            applied_filters = None

    current_chat["messages"].append(

        {

            "role": "assistant",

            "content": answer,

            "chart_json": chart_json,

            "chart_summary": chart_summary,

            "applied_filters": applied_filters
        }
    )

    st.rerun()


# ==========================================================
# MAIN HEADER (logo + title + decorative top-right icons)
# ==========================================================

st.markdown(
    """
    <div class="fw-main-header">
        <div class="fw-main-title-row">
            <div class="fw-main-title-icon">🌱</div>
            <div class="fw-main-title">
                <h1>FarmWise <span>AI</span></h1>
                <p>Your intelligent assistant for agriculture insights.</p>
            </div>
        </div>
        <div class="fw-header-icons">
            <div class="fw-header-icon-btn">☀️</div>
            <div class="fw-header-avatar">🧑‍🌾</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==========================================================
# WELCOME SCREEN
# ==========================================================

if len(current_chat["messages"]) == 0:

    st.markdown(
        """
        <div class="fw-hero">
            <div class="fw-hero-sun">☀️</div>
            <div class="fw-hero-inner">
                <div class="fw-hero-icon">🌿</div>
                <div class="fw-hero-text">
                    Ask about crop yields, rainfall, temperature,
                    pesticide use, and more — get instant insights!
                </div>
            </div>
            <div class="fw-hero-deco">🌾🌱🌿</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fw-section-label">⚡ Quick Actions</div>', unsafe_allow_html=True)

    qa_cols = st.columns(len(QUICK_ACTIONS))

    for i, (icon, color, title, sub, q) in enumerate(QUICK_ACTIONS):

        with qa_cols[i]:
            with st.container(border=True):
                st.markdown('<span class="fw-qa-marker"></span>', unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="fw-qa-icon {color}">{icon}</div>
                    <div class="fw-qa-title">{title}</div>
                    <div class="fw-qa-sub">{sub}</div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="fw-qa-wrap">', unsafe_allow_html=True)
                if st.button("Explore →", key=f"qa_{i}", use_container_width=True):
                    submit_question(q)
                st.markdown('</div>', unsafe_allow_html=True)

# ==========================================================
# METRIC / CHART DISPLAY HELPERS
# ==========================================================
# No boxed "card" wrapper - just plain markup, separated from
# the message text above by whitespace/hairline rules in CSS.
# ==========================================================


def render_metric_card(label, value, unit="hg/ha"):

    st.markdown(
        f"""
        <div class="fw-metric-inner">
            <div class="fw-metric-label">{label}</div>
            <div class="fw-metric-value">{value:,.2f}<span>{unit}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chart_title(text):

    st.markdown(f'<div class="fw-chart-title">{text}</div>', unsafe_allow_html=True)


# ==========================================================
# DISPLAY CHART FUNCTION
# ==========================================================


def display_chart(

    chart_json=None,

    chart_summary=None,

    index=0
):
    """
    Chart building now happens entirely on the backend (the LLM's
    tool call decides chart_type/filters/grouping, and build_chart()
    in chart_generator.py returns a ready Plotly figure as JSON).
    This function's only job is to render whatever came back - no
    fixed chart-type branching here anymore.
    """

    if chart_summary and not chart_json:

        # A stat-only answer (chart_type="none") - show it as a
        # metric card if it looks like one of our summary shapes.
        if "average" in chart_summary:

            metric_name = chart_summary.get("metric", "yield")

            metric_label = metric_name.title()

            units = {
                "yield": "hg/ha",
                "rainfall": "mm",
                "temperature": "°C",
                "pesticides": "tonnes",
            }

            render_metric_card(
                f"Average {metric_label}",
                chart_summary["average"],
                unit=units.get(metric_name, "")
            )

    if chart_json:

        try:
            fig = pio.from_json(chart_json)

        except Exception:
            st.warning("Couldn't render this chart.")
            return

        st.markdown('<div class="fw-chart-inner">', unsafe_allow_html=True)

        if chart_summary and chart_summary.get("rows"):
            render_chart_title(f"Based on {chart_summary['rows']} records")

        st.plotly_chart(
            fig,
            use_container_width=True,
            key=f"chart_{index}"
        )
        st.markdown('</div>', unsafe_allow_html=True)


# ==========================================================
# SHOW CHAT HISTORY (for the currently selected chat only)
# ==========================================================

for i, msg in enumerate(current_chat["messages"]):

    avatar = "🧑‍🌾" if msg["role"] == "user" else "🌱"

    with st.chat_message(msg["role"], avatar=avatar):

        st.write(msg["content"])

        if msg["role"] == "assistant":

            display_chart(

                chart_json=msg.get("chart_json"),

                chart_summary=msg.get("chart_summary"),

                index=i
            )

# ==========================================================
# CHAT INPUT
# ==========================================================

question = st.chat_input(
    "Ask anything about agriculture..."
)

# ==========================================================
# PROCESS USER QUESTION
# ==========================================================

if question:
    submit_question(question)