"""StylePick AI: a three-day-hackathon personalized commerce MVP."""

from __future__ import annotations

from concurrent.futures import Future
import hashlib
from html import escape
import logging
import os
from pathlib import Path
from threading import Thread, Timer
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import streamlit as st
from streamlit_cookies_controller import CookieController

from src.auth_session import (
    create_session_token,
    should_probe_browser_cookie,
    verify_session_token,
)
from src.database import (
    PASSWORD_SPECIAL_CHARACTERS,
    StoreDatabase,
    format_phone_input,
    normalize_email,
    normalize_nickname,
)

if TYPE_CHECKING:
    import pandas as pd


ROOT = Path(__file__).resolve().parent
PRODUCT_PATH = ROOT / "data" / "products.csv"
DATABASE_TARGET = os.environ.get("DATABASE_URL")
if not DATABASE_TARGET:
    raise RuntimeError(
        "DATABASE_URL이 필요합니다. .env.example 또는 docker-compose.yml을 참고하세요."
    )
AUTH_COOKIE_NAME = "stylepick_session"
AUTH_SESSION_TTL_SECONDS = 2 * 60 * 60
PRODUCT_ROUTE_PARAM = "product"
STORE_TAB_ROUTE_PARAM = "view"
STORE_TAB_LABELS = [
    "🛍️ 상품 탐색",
    "✨ AI 추천",
    "♥ 찜 목록",
    "🛒 장바구니·주문",
]
STORE_TAB_SLUGS = {
    STORE_TAB_LABELS[0]: "shop",
    STORE_TAB_LABELS[1]: "recommend",
    STORE_TAB_LABELS[2]: "favorites",
    STORE_TAB_LABELS[3]: "cart",
}
STORE_TAB_LABEL_BY_SLUG = {
    slug: label for label, slug in STORE_TAB_SLUGS.items()
}
AUTH_SESSION_SECRET = (
    os.environ.get("SESSION_SECRET") or DATABASE_TARGET
)
AUTH_COOKIE_COMPONENT_ENABLED = (
    os.environ.get("STYLEPICK_TEST_SYNC_STARTUP") != "1"
)
DATABASE_RECOVERY_MESSAGE = (
    "데이터베이스가 시작 중입니다. 연결이 복구되면 자동으로 다시 시도합니다."
)


def prepare_database_retry() -> None:
    """Discard a failed cached startup future before Streamlit reruns."""
    get_database_future.clear()


def is_database_unavailable_error(error: Exception) -> bool:
    """Recognize DB downtime without importing a newly added exception class.

    Streamlit Community Cloud can rerun ``app.py`` while an older
    ``src.database`` module is still cached. Comparing the exception name keeps
    a hot deployment from failing its import before the process restarts.
    """
    return type(error).__name__ == "DatabaseUnavailableError"


# Streamlit Cloud can keep ``st.cache_resource`` values across hot deploys.
# Key the database resource by its implementation so a newly deployed class
# can never reuse an instance created from an older version of database.py.
DATABASE_RESOURCE_VERSION = hashlib.sha256(
    (ROOT / "src" / "database.py").read_bytes()
).hexdigest()[:16]
st.set_page_config(
    page_title="StylePick AI",
    page_icon="✨",
    layout="wide",
)

st.markdown(
    """
    <style>
      :root {
        --sp-ink: #111827;
        --sp-muted: #64748b;
        --sp-line: #e5e7eb;
        --sp-surface: #ffffff;
        --sp-soft: #f6f7fb;
        --sp-primary: #5b4cf0;
        --sp-primary-dark: #4134cf;
        --sp-accent: #ff4d8d;
        --sp-radius: 22px;
      }
      html { scroll-behavior: smooth; }
      .stApp {
        background:
          radial-gradient(circle at 8% 0%, rgba(91,76,240,.08), transparent 26rem),
          #f8f9fc;
        color: var(--sp-ink);
        color-scheme: light;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
          "Noto Sans KR", sans-serif;
      }
      /* Keep the current screen crisp while Streamlit processes a widget rerun. */
      [data-stale="true"] {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
      }
      [data-testid="stWidgetLabel"] p,
      [data-testid="stCaptionContainer"] p,
      [data-testid="stMarkdownContainer"] > p,
      button[data-baseweb="tab"] p {
        color: var(--sp-ink) !important;
      }
      div[data-baseweb="input"] input,
      div[data-baseweb="base-input"] input {
        background: #ffffff !important;
        color: var(--sp-ink) !important;
        -webkit-text-fill-color: var(--sp-ink) !important;
      }
      iframe[title="streamlit_cookies_controller.cookie_controller.cookie_controller"],
      div[data-testid="stElementContainer"]:has(
        iframe[title="streamlit_cookies_controller.cookie_controller.cookie_controller"]
      ) {
        display: none !important;
      }
      .block-container {
        max-width: 1280px;
        padding-top: 5rem;
        padding-bottom: 6rem;
      }
      .block-container:has(.detail-page-marker) {
        position: fixed;
        inset: 3rem 0 0;
        z-index: 80;
        max-width: none;
        overflow-y: auto;
        overscroll-behavior: contain;
        box-sizing: border-box;
        padding: 4.5rem max(1rem, calc((100vw - 1280px) / 2)) 2rem;
        background:
          radial-gradient(circle at 8% 0%, rgba(91,76,240,.08), transparent 26rem),
          #f8f9fc;
      }
      .detail-page-marker {
        height: 0;
        overflow: hidden;
      }
      .st-key-detail_back_bar {
        position: fixed;
        top: 3.75rem;
        left: max(1rem, calc((100vw - 1280px) / 2));
        z-index: 95;
        width: fit-content;
        padding: .3rem;
        border: 1px solid rgba(229,231,235,.92);
        border-radius: 14px;
        background: rgba(255,255,255,.94);
        box-shadow: 0 10px 30px rgba(15,23,42,.09);
        backdrop-filter: blur(12px);
      }
      .st-key-detail_back_bar button {
        min-height: 40px;
        background: #fff;
      }
      .detail-product-visual {
        min-height: 280px;
        display: grid;
        place-items: center;
        margin-top: 0;
      }
      .detail-product-emoji {
        font-size: clamp(6rem, 9vw, 7.5rem);
        line-height: 1;
      }
      .detail-product-title {
        margin: .35rem 0 .65rem;
        font-size: clamp(2rem, 3.6vw, 3.25rem);
        line-height: 1.08;
        letter-spacing: -.045em;
        word-break: keep-all;
        overflow-wrap: anywhere;
      }
      .detail-info-marker {
        height: 0;
        overflow: hidden;
      }
      .block-container:has(.detail-page-marker)
      div[data-testid="stHorizontalBlock"]:has(.detail-product-visual) {
        align-items: flex-start;
        column-gap: clamp(2rem, 3vw, 3.25rem) !important;
        row-gap: 1.75rem !important;
      }
      .block-container:has(.detail-page-marker)
      div[data-testid="stHorizontalBlock"]:has(.detail-product-visual)
      > div[data-testid="stColumn"]:has(.detail-info-marker) {
        padding-top: .65rem;
      }
      .store-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .75rem 1rem;
        margin-bottom: 1.1rem;
        background: rgba(255,255,255,.88);
        border: 1px solid rgba(229,231,235,.9);
        border-radius: 18px;
        box-shadow: 0 10px 35px rgba(15,23,42,.06);
        backdrop-filter: blur(14px);
      }
      .st-key-store_header {
        container-name: store-header;
        container-type: inline-size;
        padding: .72rem 1rem;
        margin-bottom: 1.1rem;
        background: rgba(255,255,255,.9);
        border: 1px solid rgba(229,231,235,.9);
        border-radius: 18px;
        box-shadow: 0 10px 35px rgba(15,23,42,.06);
        backdrop-filter: blur(14px);
      }
      .st-key-store_header > div[data-testid="stVerticalBlock"] {
        gap: 0;
      }
      .st-key-store_header button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: .2rem;
        min-height: 42px;
        border-radius: 999px;
        background: #f8fafc;
        white-space: nowrap;
      }
      .st-key-store_header button p {
        margin: 0;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .st-key-store_header button svg {
        flex: 0 0 auto;
      }
      .brand-lockup {
        display: flex;
        align-items: center;
        gap: .75rem;
        transform: translateY(-6px);
      }
      .brand-mark {
        display: grid;
        place-items: center;
        width: 42px;
        height: 42px;
        color: white;
        font-weight: 900;
        border-radius: 13px;
        background: linear-gradient(135deg, var(--sp-primary), var(--sp-accent));
        box-shadow: 0 8px 18px rgba(91,76,240,.28);
      }
      .brand-name { font-weight: 900; font-size: 1.08rem; letter-spacing: -.03em; }
      .brand-caption { color: var(--sp-muted); font-size: .76rem; margin-top: .06rem; }
      .header-status { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; }
      .status-chip {
        padding: .5rem .72rem;
        color: #374151;
        background: #f8fafc;
        border: 1px solid var(--sp-line);
        border-radius: 999px;
        font-size: .8rem;
        font-weight: 700;
      }
      .hero {
        position: relative;
        overflow: hidden;
        display: grid;
        grid-template-columns: minmax(0, 1.5fr) minmax(260px, .7fr);
        gap: 2rem;
        align-items: center;
        padding: clamp(2rem, 5vw, 4.25rem);
        border-radius: 30px;
        color: white;
        margin-bottom: 1.25rem;
        background:
          radial-gradient(circle at 88% 15%, rgba(255,255,255,.23), transparent 13rem),
          linear-gradient(125deg, #3026a7, #6d4aff 54%, #e64691);
        box-shadow: 0 24px 60px rgba(67,56,202,.22);
      }
      .hero::after {
        content: "";
        position: absolute;
        width: 260px;
        height: 260px;
        right: -90px;
        bottom: -150px;
        border: 45px solid rgba(255,255,255,.1);
        border-radius: 50%;
      }
      .hero-copy, .hero-summary { position: relative; z-index: 1; }
      .hero-eyebrow {
        display: inline-flex;
        margin-bottom: .9rem;
        padding: .42rem .7rem;
        border: 1px solid rgba(255,255,255,.3);
        border-radius: 999px;
        background: rgba(255,255,255,.12);
        font-size: .77rem;
        font-weight: 800;
        letter-spacing: .06em;
      }
      .hero h1 {
        max-width: 720px;
        margin: 0 0 .75rem 0;
        font-size: clamp(2.15rem, 5vw, 4.2rem);
        line-height: 1.05;
        letter-spacing: -.055em;
      }
      .hero p {
        max-width: 620px;
        margin: 0;
        opacity: .88;
        font-size: clamp(.98rem, 1.6vw, 1.15rem);
        line-height: 1.65;
      }
      .hero-tags { display: flex; gap: .45rem; flex-wrap: wrap; margin-top: 1.2rem; }
      .hero-tag {
        padding: .42rem .68rem;
        background: rgba(255,255,255,.14);
        border-radius: 999px;
        font-size: .78rem;
        font-weight: 700;
      }
      .hero-summary {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: .65rem;
        padding: .8rem;
        background: rgba(255,255,255,.12);
        border: 1px solid rgba(255,255,255,.2);
        border-radius: 22px;
        backdrop-filter: blur(12px);
      }
      .hero-stat {
        padding: .9rem;
        background: rgba(255,255,255,.1);
        border-radius: 16px;
      }
      .hero-stat b { display: block; font-size: 1.35rem; }
      .hero-stat span { opacity: .76; font-size: .75rem; }
      .auth-hero {
        min-height: 520px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: clamp(2rem, 5vw, 4.5rem);
        color: white;
        border-radius: 30px;
        background:
          radial-gradient(circle at 85% 15%, rgba(255,255,255,.2), transparent 13rem),
          linear-gradient(145deg, #3026a7, #7048f4 58%, #ee4b91);
        box-shadow: 0 24px 60px rgba(67,56,202,.2);
      }
      .auth-hero h1 {
        max-width: 600px;
        margin: .8rem 0 1rem;
        font-size: clamp(2.5rem, 5vw, 4.8rem);
        line-height: 1.02;
        letter-spacing: -.06em;
      }
      .auth-hero p { max-width: 520px; line-height: 1.7; opacity: .88; }
      .auth-panel {
        padding: 1rem .25rem 1.5rem;
      }
      .auth-panel h2 { margin: 0; font-size: 1.65rem; letter-spacing: -.035em; }
      .auth-panel-copy { color: var(--sp-muted); margin: .4rem 0 1.3rem; }
      .section-heading { margin: 1.6rem 0 1rem; }
      .section-kicker {
        color: var(--sp-primary);
        font-size: .76rem;
        font-weight: 900;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .section-heading h2 {
        margin: .25rem 0;
        font-size: clamp(1.45rem, 3vw, 2rem);
        letter-spacing: -.04em;
      }
      .section-heading p { margin: 0; color: var(--sp-muted); }
      .product-card {
        min-height: 300px;
        background: var(--sp-surface);
        border: 1px solid var(--sp-line);
        border-radius: var(--sp-radius);
        padding: 1.15rem;
        margin-top: .5rem;
        box-shadow: 0 8px 28px rgba(15,23,42,.055);
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
      }
      .product-card:hover {
        transform: translateY(-3px);
        border-color: #cbc7ff;
        box-shadow: 0 16px 38px rgba(15,23,42,.09);
      }
      .product-visual {
        display: grid;
        place-items: center;
        min-height: 125px;
        margin-bottom: .85rem;
        border-radius: 16px;
        background: linear-gradient(145deg, #f2f0ff, #fff4f8);
      }
      .product-emoji { font-size: 3.7rem; text-align: center; filter: drop-shadow(0 7px 8px rgba(15,23,42,.12)); }
      .product-category {
        display: inline-flex;
        color: var(--sp-primary);
        background: #f1efff;
        border-radius: 999px;
        padding: .25rem .48rem;
        font-size: .72rem;
        font-weight: 800;
      }
      .product-brand {
        color: var(--sp-muted);
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .06em;
        margin-top: .65rem;
        overflow-wrap: anywhere;
      }
      .product-name {
        display: -webkit-box;
        min-height: 3.1rem;
        margin: .3rem 0;
        overflow: hidden;
        font-size: 1.06rem;
        font-weight: 800;
        line-height: 1.45;
        letter-spacing: -.025em;
        word-break: keep-all;
        overflow-wrap: anywhere;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 2;
      }
      .product-description {
        display: -webkit-box;
        min-height: 3.9rem;
        overflow: hidden;
        color: var(--sp-muted);
        font-size: .84rem;
        line-height: 1.55;
        word-break: keep-all;
        overflow-wrap: anywhere;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 3;
      }
      .product-meta {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        flex-wrap: wrap;
        gap: .3rem .65rem;
        margin-top: .8rem;
      }
      .reason {
        background: #f0fdf4; border: 1px solid #bbf7d0; color:#166534;
        border-radius: 12px; padding: .65rem; min-height: 4.2rem; font-size: .84rem;
        margin-top: .7rem;
      }
      [data-testid="stMetric"] {
        background:white; border:1px solid var(--sp-line); border-radius:16px; padding:14px;
      }
      [data-testid="stSidebar"] [data-testid="stExpander"] {
        overflow: hidden;
        border: 1px solid var(--sp-line);
        border-radius: 16px;
        background: #fff;
      }
      [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        min-height: 54px;
        font-weight: 750;
      }
      button[kind="primary"] {
        background: linear-gradient(110deg, var(--sp-primary), #7c3aed) !important;
        border: 0 !important;
      }
      .stButton button, .stFormSubmitButton button { min-height: 44px; border-radius: 12px; }
      div[data-baseweb="tab-list"] {
        gap: .25rem;
        padding: .3rem;
        background: white;
        border: 1px solid var(--sp-line);
        border-radius: 15px;
      }
      button[data-baseweb="tab"] { min-height: 44px; border-radius: 11px; padding: .55rem .9rem; }
      button[data-baseweb="tab"][aria-selected="true"] { background: #f1efff; }
      .trust-strip {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: .8rem;
        margin: 3rem 0 1.25rem;
      }
      .trust-item {
        padding: 1.2rem;
        background: white;
        border: 1px solid var(--sp-line);
        border-radius: 18px;
      }
      .trust-item b { display: block; margin-bottom: .25rem; }
      .trust-item span { color: var(--sp-muted); font-size: .82rem; line-height: 1.5; }
      .store-footer {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.6rem 0 .5rem;
        color: var(--sp-muted);
        border-top: 1px solid var(--sp-line);
        font-size: .78rem;
      }
      .store-footer b { color: var(--sp-ink); }

      @container store-header (max-width: 720px) {
        .st-key-store_header div[data-testid="stHorizontalBlock"] {
          display: grid !important;
          grid-template-columns:
            42px minmax(82px, 1fr)
            minmax(56px, 64px) minmax(56px, 64px) !important;
          align-items: center;
          gap: .35rem;
        }
        .st-key-store_header div[data-testid="stHorizontalBlock"]
        > div[data-testid="stColumn"] {
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
          width: auto !important;
          height: 42px;
          min-width: 0 !important;
          max-width: none !important;
          flex: none !important;
        }
        .st-key-store_header div[data-testid="stHorizontalBlock"]
        > div[data-testid="stColumn"]
        > div[data-testid="stVerticalBlock"] {
          width: 100%;
          height: 42px;
          justify-content: center;
          gap: 0;
        }
        .st-key-store_header .brand-lockup {
          height: 42px;
          justify-content: center;
        }
        .st-key-store_header .brand-name,
        .st-key-store_header .brand-caption {
          display: none;
        }
        .st-key-store_header button {
          width: 100%;
          height: 42px;
          min-height: 42px;
          padding: 0 .45rem;
          font-size: .76rem;
          overflow: hidden;
          text-overflow: ellipsis;
        }
      }

      @media (max-width: 1200px) {
        .hero {
          grid-template-columns: 1fr;
        }
        .hero-summary {
          max-width: 520px;
        }
        .header-status .status-chip:first-child {
          display: none;
        }
        div[data-testid="stHorizontalBlock"]:has(.auth-hero) {
          flex-wrap: wrap;
        }
        div[data-testid="stHorizontalBlock"]:has(.auth-hero)
        > div[data-testid="stColumn"] {
          min-width: min(100%, 420px);
          flex: 1 1 420px;
        }
        div[data-testid="stHorizontalBlock"]:has(.product-card) {
          flex-wrap: wrap;
          gap: .75rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.product-card)
        > div[data-testid="stColumn"] {
          flex: 1 1 calc(50% - .75rem) !important;
          width: calc(50% - .75rem) !important;
          min-width: min(100%, 260px) !important;
        }
        .block-container:has(.detail-page-marker)
        div[data-testid="stHorizontalBlock"]:has(.product-card)
        > div[data-testid="stColumn"] {
          flex-basis: 100% !important;
          width: 100% !important;
          min-width: 100% !important;
        }
        div[data-testid="stHorizontalBlock"]:has(
          input[aria-label="상품 검색"]
        ) {
          flex-wrap: wrap;
          gap: .65rem;
        }
        div[data-testid="stHorizontalBlock"]:has(
          input[aria-label="상품 검색"]
        ) > div[data-testid="stColumn"] {
          flex: 1 1 190px !important;
          width: auto !important;
          min-width: min(100%, 190px) !important;
        }
      }

      @media (min-width: 901px) {
        [data-testid="stMain"]:has(.detail-page-marker) {
          transform: translateZ(0);
        }
        .block-container:has(.detail-page-marker) {
          position: relative;
          inset: auto;
          z-index: auto;
          max-width: 1280px;
          min-height: calc(100vh - 3rem);
          overflow: visible;
          padding: 4.5rem 1rem 2rem;
        }
        .st-key-detail_back_bar {
          position: fixed;
          top: 3.45rem;
          left: 1rem;
        }
      }

      @media (max-width: 900px) {
        .stApp:has(.detail-page-marker) [data-testid="stSidebar"],
        .stApp:has(.detail-page-marker)
        [data-testid="stSidebarCollapsedControl"] {
          display: none !important;
        }
        .st-key-detail_back_bar {
          top: 3.45rem;
        }
        .block-container { padding-left: 1.15rem; padding-right: 1.15rem; }
        .hero { grid-template-columns: 1fr; }
        .hero-summary { max-width: 520px; }
        .header-status .status-chip:first-child { display: none; }
        div[data-testid="stHorizontalBlock"]:has(.auth-hero) {
          flex-wrap: wrap;
        }
        div[data-testid="stHorizontalBlock"]:has(.auth-hero) > div[data-testid="stColumn"] {
          min-width: min(100%, 420px);
          flex: 1 1 420px;
        }
      }

      @media (max-width: 640px) {
        .block-container {
          padding: 4.75rem .8rem 7.4rem;
        }
        .block-container:has(.detail-page-marker) {
          padding-top: 4.35rem;
        }
        .st-key-detail_back_bar {
          top: 3.45rem;
          left: .75rem;
        }
        .detail-product-visual { min-height: 220px; }
        .detail-product-emoji { font-size: 5.75rem; }
        .detail-product-title { font-size: 2rem; }
        .block-container:has(.detail-page-marker)
        div[data-testid="stHorizontalBlock"]:has(.detail-product-visual) {
          gap: 1.75rem !important;
        }
        .block-container:has(.detail-page-marker)
        div[data-testid="stHorizontalBlock"]:has(.detail-product-visual)
        > div[data-testid="stColumn"]:has(.detail-info-marker) {
          padding-top: .35rem;
        }
        .store-header {
          position: sticky;
          top: .45rem;
          z-index: 90;
          padding: .58rem .65rem;
          border-radius: 15px;
        }
        .st-key-store_header {
          position: sticky;
          top: .45rem;
          z-index: 90;
          padding: .52rem .58rem;
          border-radius: 15px;
        }
        .st-key-store_header div[data-testid="stHorizontalBlock"] {
          display: grid !important;
          grid-template-columns:
            42px minmax(82px, 1fr)
            minmax(56px, 64px) minmax(56px, 64px) !important;
          align-items: center;
          gap: .35rem;
        }
        .st-key-store_header div[data-testid="stHorizontalBlock"]
        > div[data-testid="stColumn"] {
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
          width: auto !important;
          height: 42px;
          min-width: 0 !important;
          max-width: none !important;
          flex: none !important;
        }
        .st-key-store_header div[data-testid="stHorizontalBlock"]
        > div[data-testid="stColumn"]
        > div[data-testid="stVerticalBlock"] {
          width: 100%;
          height: 42px;
          justify-content: center;
          gap: 0;
        }
        .st-key-store_header .brand-lockup {
          height: 42px;
          justify-content: center;
        }
        .st-key-store_header .brand-name,
        .st-key-store_header .brand-caption {
          display: none;
        }
        .st-key-store_header button {
          width: 100%;
          height: 42px;
          min-height: 42px;
          padding-block: 0;
          padding-inline: .55rem;
          font-size: .76rem;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .brand-caption, .header-status .status-chip:first-child { display: none; }
        .brand-mark { width: 38px; height: 38px; }
        .status-chip { padding: .43rem .58rem; font-size: .73rem; }
        .hero {
          grid-template-columns: 1fr;
          gap: 1.2rem;
          padding: 1.65rem 1.25rem;
          border-radius: 22px;
        }
        .hero h1 { font-size: 2.35rem; }
        .hero-summary { grid-template-columns: repeat(2, 1fr); padding: .55rem; }
        .hero-stat { padding: .7rem; }
        .auth-hero { min-height: 320px; padding: 2rem 1.35rem; border-radius: 22px; }
        .auth-panel { padding: .5rem .1rem 1rem; }
        .section-heading { margin-top: 1.2rem; }
        div[data-testid="stHorizontalBlock"]:has(.product-card) {
          flex-wrap: wrap;
          gap: .35rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.product-card) > div[data-testid="stColumn"] {
          flex: 1 1 100% !important;
          width: 100% !important;
          min-width: 100% !important;
        }
        .product-card { min-height: 0; }
        .product-name, .product-description {
          min-height: 0;
          -webkit-line-clamp: initial;
        }
        .trust-strip { grid-template-columns: 1fr; margin-top: 2rem; }
        .store-footer { flex-direction: column; }
        body:has(.store-shell-marker) div[data-testid="stTabs"] > div[data-baseweb="tab-list"] {
          position: fixed;
          left: .55rem;
          right: .55rem;
          bottom: .55rem;
          z-index: 999;
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: .2rem;
          padding: .35rem;
          box-shadow: 0 16px 45px rgba(15,23,42,.2);
          border-radius: 18px;
        }
        body:has(.store-shell-marker) button[data-baseweb="tab"] {
          min-width: 0;
          padding: .52rem .15rem;
        }
        body:has(.store-shell-marker) button[data-baseweb="tab"] p {
          max-width: 100%;
          overflow: hidden;
          font-size: 0;
        }
        body:has(.store-shell-marker) button[data-baseweb="tab"] p::first-letter {
          font-size: 1.15rem;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

class TestCookieController:
    """No-browser adapter for Streamlit AppTest integration runs."""

    def get(self, _name: str):
        return None

    def set(self, _name: str, _value: str, **_options) -> None:
        return None

    def remove(self, _name: str, **_options) -> None:
        return None


if not AUTH_COOKIE_COMPONENT_ENABLED:
    auth_cookie_controller = TestCookieController()
else:
    auth_cookie_controller = CookieController(key="stylepick_auth_cookies")

# Keep authentication in one stable delta slot. On a successful login the same
# slot is emptied before any database/model wait, so the browser cannot retain
# auth elements underneath the storefront while Streamlit reconciles the page.
auth_page_slot = st.empty()


@st.cache_data
def get_products() -> pd.DataFrame:
    from src.catalog import load_products

    return load_products(PRODUCT_PATH)


def build_database(database_url: str) -> StoreDatabase:
    """Connect quickly in production; initialize local and test databases."""
    is_production = os.environ.get("APP_ENV", "development").lower() == "production"
    cached_database = StoreDatabase(
        database_url,
        initialize_schema=not is_production,
    )
    if not is_production:
        cached_database.seed_products(get_products())
        if os.environ.get("DEMO_MODE", "true").lower() == "true":
            cached_database.ensure_demo_user()
    cached_database.catalog_snapshot = cached_database.load_products()
    return cached_database


def start_daemon_future(
    target,
    *args,
    thread_name: str,
    delay_seconds: float = 0,
) -> Future:
    future = Future()

    def run() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(target(*args))
        except BaseException as error:
            future.set_exception(error)

    worker = Thread(target=run, name=thread_name, daemon=True)
    if delay_seconds > 0:
        timer = Timer(delay_seconds, worker.start)
        timer.daemon = True
        timer.start()
    else:
        worker.start()
    return future


@st.cache_resource(show_spinner=False)
def get_database_future(
    database_url: str,
    resource_version: str,
) -> Future:
    del resource_version
    return start_daemon_future(
        build_database,
        database_url,
        thread_name="stylepick-database",
    )


@st.cache_resource(show_spinner=False)
def get_database_sync(
    database_url: str,
    resource_version: str,
) -> StoreDatabase:
    del resource_version
    return build_database(database_url)


class LazyDatabase:
    """Delay waiting for the remote DB until an authentication action needs it."""

    def __init__(self, future: Future) -> None:
        self.future = future

    def __getattr__(self, name: str):
        return getattr(self.future.result(), name)


if os.environ.get("STYLEPICK_TEST_SYNC_STARTUP") == "1":
    database_future = Future()
    database_future.set_result(
        get_database_sync(DATABASE_TARGET, DATABASE_RESOURCE_VERSION)
    )
else:
    database_future = get_database_future(
        DATABASE_TARGET,
        DATABASE_RESOURCE_VERSION,
    )
database = LazyDatabase(database_future)
RECOMMENDER_BACKEND = "cnn"


@st.cache_data(ttl=300, show_spinner=False)
def get_database_products(
    database_url: str,
    _database: StoreDatabase,
) -> pd.DataFrame:
    """Use the catalog fetched during process startup, outside click paths."""
    return _database.catalog_snapshot.copy()


@st.cache_data(ttl=300, show_spinner=False)
def get_storefront_snapshot(
    database_url: str,
    user_id: int,
    _database: StoreDatabase,
) -> dict:
    return _database.load_storefront_snapshot(user_id)


@st.cache_resource(show_spinner=False)
def get_recommendation_model_future(
    backend: str,
    catalog_fingerprint: tuple,
) -> Future:
    """Load the recommender while the visitor uses the authentication screen."""
    return start_daemon_future(
        build_recommendation_model,
        backend,
        thread_name="stylepick-recommender",
        delay_seconds=0.75,
    )


@st.cache_resource(show_spinner=False)
def get_recommendation_model_sync(
    backend: str,
    catalog_fingerprint: tuple,
):
    return build_recommendation_model(backend)


def build_recommendation_model(backend: str):
    from src.catalog import load_products
    from src.recommender import fit_recommender

    return fit_recommender(load_products(PRODUCT_PATH), backend=backend)


def rank_products(**kwargs) -> pd.DataFrame:
    from src.recommender import recommend

    return recommend(**kwargs)


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_user(
    database_url: str,
    user_id: int,
    _database: StoreDatabase,
) -> dict:
    return _database.get_user(user_id)


@st.cache_data(ttl=10, show_spinner=False)
def get_cached_behavior_summary(
    database_url: str,
    user_id: int,
    _database: StoreDatabase,
) -> dict:
    return _database.behavior_summary(user_id)


@st.cache_data(ttl=10, show_spinner=False)
def get_cached_behavior_weights(
    database_url: str,
    user_id: int,
    _database: StoreDatabase,
) -> dict:
    return _database.user_behavior_weights(user_id)


@st.cache_data(ttl=30, show_spinner=False)
def get_cached_trend_scores(
    database_url: str,
    days: int,
    _database: StoreDatabase,
) -> dict:
    return _database.trend_scores(days=days)


@st.cache_data(ttl=15, show_spinner=False)
def get_cached_purchased_ids(
    database_url: str,
    user_id: int,
    _database: StoreDatabase,
) -> set[str]:
    return _database.purchased_product_ids(user_id)


@st.cache_data(ttl=10, show_spinner=False)
def get_cached_order_history(
    database_url: str,
    user_id: int,
    limit: int,
    _database: StoreDatabase,
) -> list[dict]:
    return _database.list_orders(user_id, limit=limit)


@st.cache_data(ttl=15, show_spinner=False)
def get_cached_product_reviews(
    database_url: str,
    product_id: str,
    _database: StoreDatabase,
) -> list[dict]:
    return _database.list_product_reviews(product_id)


def queue_auth_cookie(
    action: str,
    token: str = "",
    expires_at: int = 0,
) -> None:
    st.session_state.auth_cookie_action = (action, token, int(expires_at))


def render_auth_cookie_action() -> None:
    """Apply a queued signed login cookie through a Streamlit component."""
    queued = st.session_state.pop("auth_cookie_action", None)
    if not queued:
        return
    action, token, expires_at = queued
    is_production = (
        os.environ.get("APP_ENV", "development").lower() == "production"
    )
    if action == "set":
        max_age = max(1, int(expires_at) - int(time.time()))
        auth_cookie_controller.set(
            AUTH_COOKIE_NAME,
            token,
            path="/",
            max_age=max_age,
            secure=is_production,
            same_site="lax",
        )
    elif action == "clear":
        auth_cookie_controller.set(
            AUTH_COOKIE_NAME,
            "",
            path="/",
            max_age=0,
            secure=is_production,
            same_site="lax",
        )


def remember_user_session(user_id: int) -> int:
    token, claims = create_session_token(
        user_id,
        AUTH_SESSION_SECRET,
        ttl_seconds=AUTH_SESSION_TTL_SECONDS,
    )
    queue_auth_cookie("set", token, claims.expires_at)
    return claims.expires_at


def get_remembered_user(user_id: int) -> dict:
    """Retry one transient pooled-connection failure during cookie restore."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return database.get_user(user_id)
        except ValueError:
            raise
        except Exception as error:
            last_error = error
            if attempt == 0:
                # DBUtils normally pings idle sockets, but a free remote MySQL
                # node can invalidate the whole pool while it wakes. Rebuild
                # the pool before retrying instead of returning a manual error.
                database.reset_connection_pool()
                time.sleep(0.2)
    assert last_error is not None
    raise last_error


def initialize_auth() -> None:
    st.session_state.pop("auth_restore_error", None)
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"session_{uuid4().hex[:12]}"
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if st.session_state.user_id:
        expires_at = int(st.session_state.get("auth_expires_at") or 0)
        if expires_at and expires_at <= int(time.time()):
            logout_user()
        elif not expires_at:
            st.session_state.auth_expires_at = remember_user_session(
                int(st.session_state.user_id)
            )
    if (
        not st.session_state.user_id
        and not st.session_state.get("auth_cookie_restore_blocked")
    ):
        raw_token = (
            auth_cookie_controller.get(AUTH_COOKIE_NAME)
            or st.context.cookies.get(AUTH_COOKIE_NAME)
        )
        if raw_token:
            claims = verify_session_token(
                raw_token,
                AUTH_SESSION_SECRET,
            )
            if claims is None:
                queue_auth_cookie("clear")
                st.session_state.auth_cookie_restore_blocked = True
            else:
                try:
                    user = get_remembered_user(claims.user_id)
                except ValueError:
                    queue_auth_cookie("clear")
                    st.session_state.auth_cookie_restore_blocked = True
                except Exception:
                    logging.exception(
                        "StylePick remembered-login database lookup failed"
                    )
                    st.session_state.auth_restore_error = True
                else:
                    login_user(
                        user,
                        persist_session=False,
                        expires_at=claims.expires_at,
                    )
    if (
        os.environ.get("STYLEPICK_TEST_AUTOLOGIN") == "1"
        and not st.session_state.user_id
    ):
        login_user(
            database.ensure_demo_user(),
            persist_session=False,
            expires_at=int(time.time()) + AUTH_SESSION_TTL_SECONDS,
        )


def login_user(
    user: dict,
    *,
    persist_session: bool = True,
    expires_at: int | None = None,
) -> None:
    user_id = int(user["id"])
    # Finish the small, single-query storefront snapshot before replacing the
    # authentication page. This produces one atomic screen transition instead
    # of briefly mixing old auth elements with an incomplete storefront.
    storefront_snapshot = database.load_storefront_snapshot(user_id)
    st.session_state.user_id = user_id
    st.session_state.current_user = user
    st.session_state.loaded_user_id = None
    st.session_state.last_order = None
    st.session_state.storefront_snapshot_ready = storefront_snapshot
    if persist_session:
        st.session_state.auth_expires_at = remember_user_session(user_id)
    else:
        st.session_state.auth_expires_at = int(
            expires_at or (time.time() + AUTH_SESSION_TTL_SECONDS)
        )


def submit_login() -> None:
    st.session_state.pop("login_error", None)
    try:
        login_user(
            database.authenticate(
                st.session_state.get("login_email", ""),
                st.session_state.get("login_password", ""),
            ),
            persist_session=bool(
                st.session_state.get("remember_login", True)
            ),
        )
        st.session_state.auth_notice = (
            "DB에 저장된 계정 정보를 확인하고 로그인했습니다."
        )
    except ValueError as error:
        st.session_state.login_error = str(error)
    except RuntimeError as error:
        if not is_database_unavailable_error(error):
            raise
        prepare_database_retry()
        st.session_state.login_error = DATABASE_RECOVERY_MESSAGE


def start_demo() -> None:
    try:
        login_user(database.ensure_demo_user())
    except RuntimeError as error:
        if not is_database_unavailable_error(error):
            raise
        prepare_database_retry()
        st.session_state.login_error = DATABASE_RECOVERY_MESSAGE


def submit_signup() -> None:
    st.session_state.pop("signup_error", None)
    signup_password = st.session_state.get("signup_password", "")
    signup_confirm = st.session_state.get("signup_confirm", "")
    if signup_password != signup_confirm:
        st.session_state.signup_error = "비밀번호 확인이 일치하지 않습니다."
        return
    try:
        user = database.register_user(
            st.session_state.get("signup_email", ""),
            signup_password,
            st.session_state.get("signup_nickname", ""),
            st.session_state.get("signup_phone", ""),
        )
        login_user(user)
        st.session_state.auth_notice = (
            "회원가입 정보가 DB에 저장되고 로그인되었습니다."
        )
    except ValueError as error:
        st.session_state.signup_error = str(error)
    except RuntimeError as error:
        if not is_database_unavailable_error(error):
            raise
        prepare_database_retry()
        st.session_state.signup_error = DATABASE_RECOVERY_MESSAGE


def logout_user() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.user_id = None
    st.session_state.auth_cookie_restore_blocked = True
    queue_auth_cookie("clear")


def wait_for_pending_cart_writes() -> None:
    pending_writes = list(st.session_state.get("pending_cart_writes", []))
    st.session_state.pending_cart_writes = []
    for pending_write in pending_writes:
        pending_write.result()


def delete_current_user() -> None:
    st.session_state.pop("delete_account_error", None)
    try:
        wait_for_pending_cart_writes()
        database.delete_user(
            int(st.session_state.user_id),
            st.session_state.get("delete_account_password", ""),
        )
    except ValueError as error:
        st.session_state.delete_account_error = str(error)
        return
    logout_user()
    st.session_state.account_deleted_notice = True


def save_profile_settings() -> None:
    st.session_state.pop("profile_error", None)
    try:
        saved_nickname = st.session_state.nickname
        interests = list(st.session_state.get("profile_interests", []))
        budget = tuple(st.session_state.get("profile_budget", (0, 250_000)))
        database.save_profile(
            int(st.session_state.user_id),
            saved_nickname,
            interests,
            budget,
        )
        st.session_state.nickname = saved_nickname
        st.session_state.interests = interests
        st.session_state.budget = budget
        if st.session_state.get("current_user"):
            st.session_state.current_user["nickname"] = saved_nickname
        get_cached_user.clear()
        st.session_state.profile_saved_notice = True
    except ValueError as error:
        st.session_state.profile_error = str(error)


def verify_header_profile_password() -> None:
    st.session_state.pop("header_profile_error", None)
    try:
        account = database.verify_user_password(
            int(st.session_state.user_id),
            st.session_state.get("header_profile_password", ""),
        )
        st.session_state.header_profile_verified = True
        st.session_state.header_profile_password = ""
        st.session_state.header_profile_nickname = st.session_state.nickname
        st.session_state.header_profile_phone = format_phone_input(
            str(account.get("phone_number") or "")
        )
    except ValueError as error:
        st.session_state.header_profile_verified = False
        st.session_state.header_profile_error = str(error)


def save_header_account_settings() -> None:
    st.session_state.pop("header_profile_error", None)
    new_password = st.session_state.get("header_new_password", "")
    if new_password != st.session_state.get("header_confirm_password", ""):
        st.session_state.header_profile_error = (
            "새 비밀번호 확인이 일치하지 않습니다."
        )
        return
    try:
        nickname = (
            st.session_state.get("header_profile_nickname", "").strip()
            or "게스트"
        )
        phone = st.session_state.get("header_profile_phone", "")
        database.update_account_settings(
            int(st.session_state.user_id),
            nickname,
            phone,
            new_password=new_password,
        )
        st.session_state.nickname = nickname
        st.session_state.profile_nickname = nickname
        st.session_state.current_user["nickname"] = nickname
        st.session_state.current_user["phone_number"] = phone
        st.session_state.header_new_password = ""
        st.session_state.header_confirm_password = ""
        st.session_state.header_profile_verified = False
        st.session_state.header_profile_notice = "계정 정보가 저장되었습니다."
        get_cached_user.clear()
    except ValueError as error:
        st.session_state.header_profile_error = str(error)


def check_signup_email_availability() -> None:
    st.session_state.pop("signup_email_error", None)
    email = st.session_state.get("signup_email", "")
    st.session_state.checked_signup_email = normalize_email(email)
    try:
        if database.email_is_available(email):
            st.session_state.verified_signup_email = normalize_email(email)
        else:
            st.session_state.verified_signup_email = None
            st.session_state.signup_email_error = "이미 가입된 이메일입니다."
    except ValueError as error:
        st.session_state.verified_signup_email = None
        st.session_state.signup_email_error = str(error)
    except RuntimeError as error:
        if not is_database_unavailable_error(error):
            raise
        prepare_database_retry()
        st.session_state.verified_signup_email = None
        st.session_state.signup_email_error = DATABASE_RECOVERY_MESSAGE


def check_signup_nickname_availability() -> None:
    st.session_state.pop("signup_nickname_error", None)
    nickname = st.session_state.get("signup_nickname", "")
    normalized_nickname = normalize_nickname(nickname).casefold()
    st.session_state.checked_signup_nickname = normalized_nickname
    try:
        if database.nickname_is_available(nickname):
            st.session_state.verified_signup_nickname = normalized_nickname
        else:
            st.session_state.verified_signup_nickname = None
            st.session_state.signup_nickname_error = "이미 사용 중인 닉네임입니다."
    except ValueError as error:
        st.session_state.verified_signup_nickname = None
        st.session_state.signup_nickname_error = str(error)
    except RuntimeError as error:
        if not is_database_unavailable_error(error):
            raise
        prepare_database_retry()
        st.session_state.verified_signup_nickname = None
        st.session_state.signup_nickname_error = DATABASE_RECOVERY_MESSAGE


def format_signup_phone() -> None:
    st.session_state.signup_phone = format_phone_input(
        st.session_state.get("signup_phone", "")
    )


def enable_live_phone_format() -> None:
    """Add client-side formatting while keeping server-side validation authoritative."""
    st.iframe(
        """
        <script>
        (() => {
          const parentDocument = window.parent.document;
          const formatPhone = (rawValue) => {
            const digits = rawValue.replace(/\\D/g, "").slice(0, 11);
            if (digits.length <= 3) return digits;
            if (digits.length <= 7) {
              return `${digits.slice(0, 3)}-${digits.slice(3)}`;
            }
            return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
          };
          const attachFormatter = () => {
            const input = parentDocument.querySelector(
              'input[aria-label="전화번호"]'
            );
            if (!input || input.dataset.stylepickPhoneFormatter === "1") {
              return Boolean(input);
            }
            input.dataset.stylepickPhoneFormatter = "1";
            input.addEventListener("input", () => {
              const formatted = formatPhone(input.value);
              if (formatted === input.value) return;
              const valueSetter = Object.getOwnPropertyDescriptor(
                window.parent.HTMLInputElement.prototype,
                "value"
              ).set;
              valueSetter.call(input, formatted);
              input.dispatchEvent(
                new window.parent.Event("input", { bubbles: true })
              );
              input.setSelectionRange(formatted.length, formatted.length);
            });
            return true;
          };
          if (!attachFormatter()) {
            const observer = new MutationObserver(() => {
              if (attachFormatter()) observer.disconnect();
            });
            observer.observe(parentDocument.body, {
              childList: true,
              subtree: true
            });
            window.setTimeout(() => observer.disconnect(), 10000);
          }
        })();
        </script>
        """,
        height=1,
        width=1,
        tab_index=-1,
    )


def render_auth_probe() -> None:
    """Render no auth controls while the browser cookie component starts."""
    st.markdown(
        """
        <style>
          .auth-probe-card {
            max-width: 420px;
            margin: 18vh auto 0;
            padding: 1rem 1.2rem;
            text-align: center;
            color: #64748b;
            background: rgba(255,255,255,.9);
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            box-shadow: 0 14px 40px rgba(15,23,42,.07);
          }
        </style>
        <div class="auth-probe-card">
          로그인 상태를 확인하고 있어요.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_auth() -> None:
    intro_col, form_col = st.columns([1.08, .92], gap="large")
    with intro_col:
        st.markdown(
            """
            <section class="auth-hero">
              <div>
                <span class="hero-eyebrow">EXPLAINABLE AI COMMERCE</span>
                <h1>내 취향을 아는<br>쇼핑의 시작.</h1>
                <p>
                  검색, 찜, 장바구니 행동을 안전하게 분리 저장하고
                  왜 추천했는지 설명하는 개인화 쇼핑을 경험해 보세요.
                </p>
              </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with form_col:
        st.markdown(
            """
            <div class="auth-panel">
              <h2>StylePick AI 시작하기</h2>
              <p class="auth-panel-copy">로그인하거나 새 계정을 만들어 취향을 저장하세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state.pop("account_deleted_notice", False):
            st.success("회원 정보와 연결 데이터가 모두 삭제되었습니다.")
        login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
        with login_tab:
            with st.form("login_form"):
                st.text_input(
                    "이메일",
                    placeholder="name@example.com",
                    key="login_email",
                )
                st.text_input("비밀번호", type="password", key="login_password")
                st.checkbox(
                    "로그인 유지",
                    value=True,
                    key="remember_login",
                    help=(
                        "새로고침하거나 브라우저를 닫았다 다시 접속해도 "
                        "최대 2시간 동안 로그인 상태를 유지합니다."
                    ),
                )
                st.form_submit_button(
                    "로그인",
                    type="primary",
                    width="stretch",
                    on_click=submit_login,
                )
            if login_error := st.session_state.get("login_error"):
                st.error(login_error)
            st.button(
                "데모 계정으로 바로 시작",
                width="stretch",
                on_click=start_demo,
            )
            st.caption("데모 계정은 로컬 시연용이며 실제 결제는 발생하지 않습니다.")
        with signup_tab:
            signup_email = st.text_input(
                "이메일",
                key="signup_email",
                max_chars=120,
            )
            st.button(
                "이메일 중복 확인",
                key="check_signup_email",
                width="stretch",
                on_click=check_signup_email_availability,
            )
            email_verified = (
                bool(signup_email.strip())
                and st.session_state.get("verified_signup_email")
                == normalize_email(signup_email)
            )
            if email_verified:
                st.success("사용 가능한 이메일입니다.")
            elif (
                st.session_state.get("checked_signup_email")
                == normalize_email(signup_email)
                and (email_error := st.session_state.get("signup_email_error"))
            ):
                st.error(email_error)
            else:
                st.caption("이메일 중복 확인이 필요합니다.")

            signup_nickname = st.text_input(
                "닉네임",
                key="signup_nickname",
                max_chars=30,
            )
            st.button(
                "닉네임 중복 확인",
                key="check_signup_nickname",
                width="stretch",
                on_click=check_signup_nickname_availability,
            )
            nickname_verified = (
                bool(signup_nickname.strip())
                and st.session_state.get("verified_signup_nickname")
                == normalize_nickname(signup_nickname).casefold()
            )
            if nickname_verified:
                st.success("사용 가능한 닉네임입니다.")
            elif (
                st.session_state.get("checked_signup_nickname")
                == normalize_nickname(signup_nickname).casefold()
                and (
                    nickname_error
                    := st.session_state.get("signup_nickname_error")
                )
            ):
                st.error(nickname_error)
            else:
                st.caption("닉네임 중복 확인이 필요합니다.")

            st.text_input(
                "전화번호",
                key="signup_phone",
                placeholder="010-1234-5678",
                max_chars=20,
                on_change=format_signup_phone,
            )
            enable_live_phone_format()
            st.text_input(
                "비밀번호",
                type="password",
                key="signup_password",
            )
            st.caption(
                "8자 이상 · 영문 대문자 1개 이상 · 특수문자 1개 이상"
            )
            st.caption(f"허용 특수문자: {PASSWORD_SPECIAL_CHARACTERS}")
            st.text_input(
                "비밀번호 확인",
                type="password",
                key="signup_confirm",
            )
            st.button(
                "회원가입",
                type="primary",
                width="stretch",
                disabled=not (email_verified and nickname_verified),
                on_click=submit_signup,
            )
            if signup_error := st.session_state.get("signup_error"):
                st.error(signup_error)


def initialize_state(snapshot: dict) -> None:
    user_id = int(st.session_state.user_id)
    if st.session_state.get("loaded_user_id") == user_id:
        return
    profile = snapshot["profile"]
    st.session_state.nickname = profile["nickname"]
    st.session_state.interests = profile["interests"]
    st.session_state.budget = profile["budget"]
    st.session_state.profile_nickname = profile["nickname"]
    st.session_state.profile_interests = profile["interests"]
    st.session_state.profile_budget = profile["budget"]
    st.session_state.header_profile_verified = False
    st.session_state.header_profile_password = ""
    st.session_state.header_new_password = ""
    st.session_state.header_confirm_password = ""
    st.session_state.favorites = snapshot["favorites"]
    st.session_state.cart = snapshot["cart"]
    st.session_state.behavior_summary = snapshot["behavior_summary"]
    st.session_state.behavior_weights = snapshot["behavior_weights"]
    st.session_state.trend_scores = snapshot["trend_scores"]
    st.session_state.purchased_ids = snapshot["purchased_ids"]
    st.session_state.order_history = snapshot["order_history"]
    st.session_state.last_order = None
    st.session_state.loaded_user_id = user_id


def toggle_favorite(product_id: str) -> None:
    added = database.toggle_favorite(
        int(st.session_state.user_id),
        product_id,
        st.session_state.session_id,
    )
    if added:
        st.session_state.favorites.add(product_id)
        st.toast("관심 상품으로 저장했어요. 추천에 반영됩니다.")
    else:
        st.session_state.favorites.discard(product_id)
        st.toast("찜 목록에서 제거했어요.")


def add_to_cart(product_id: str) -> None:
    try:
        wait_for_pending_cart_writes()
        quantity = database.add_to_cart(
            int(st.session_state.user_id),
            product_id,
            st.session_state.session_id,
        )
        st.session_state.cart[product_id] = quantity
        st.toast("장바구니에 담았습니다.")
    except ValueError as error:
        st.error(str(error))


def remove_from_cart(product_id: str) -> None:
    wait_for_pending_cart_writes()
    database.remove_cart_item(
        int(st.session_state.user_id),
        product_id,
        st.session_state.session_id,
    )
    st.session_state.cart.pop(product_id, None)


def refresh_catalog_stock(order: dict) -> None:
    """Apply committed order stock to the in-memory catalog immediately."""
    catalog_snapshot = database.catalog_snapshot
    items = order.get("items", [])
    if any("remaining_stock" not in item for item in items):
        # A Streamlit hot deployment can briefly retain the cached database
        # object from the previous app version. Reload from the database when
        # that object returns the older order payload shape.
        database.catalog_snapshot = database.load_products()
        get_database_products.clear()
        return
    for item in items:
        product_id = str(item["product_id"])
        remaining_stock = int(item["remaining_stock"])
        catalog_snapshot.loc[
            catalog_snapshot["id"] == product_id,
            "stock",
        ] = remaining_stock
    get_database_products.clear()


def complete_order() -> None:
    st.session_state.pop("checkout_error", None)
    try:
        wait_for_pending_cart_writes()
        order = database.create_order(
            int(st.session_state.user_id),
            st.session_state.session_id,
        )
        refresh_catalog_stock(order)
        st.session_state.last_order = order
        st.session_state.order_history = [
            order,
            *st.session_state.get("order_history", []),
        ][:5]
        st.session_state.cart = {}
        st.session_state.checkout_notice = (
            f"모의결제가 완료되었습니다. 결제 금액 {int(order['total']):,}원"
        )
    except ValueError as error:
        st.session_state.checkout_error = str(error)


def reset_last_order() -> None:
    st.session_state.last_order = None


ORDER_STATUS_LABELS = {
    "PAID_DEMO": "결제 완료",
    "PREPARING_DEMO": "상품 준비",
    "SHIPPING_DEMO": "배송 중",
    "DELIVERED_DEMO": "배송 완료",
    "CANCELED_DEMO": "주문 취소 완료",
}


def order_status_label(status: str) -> str:
    return ORDER_STATUS_LABELS.get(str(status), str(status))


def clear_order_caches() -> None:
    """Invalidate remote snapshots without synchronously reloading them."""
    get_database_products.clear()
    get_storefront_snapshot.clear()
    get_cached_purchased_ids.clear()
    get_cached_order_history.clear()
    get_cached_behavior_summary.clear()
    get_cached_behavior_weights.clear()
    get_cached_product_reviews.clear()


def cancel_demo_order(order_id: str) -> None:
    st.session_state.pop("order_action_error", None)
    try:
        wait_for_pending_cart_writes()
        result = database.cancel_order(
            int(st.session_state.user_id),
            order_id,
            st.session_state.session_id,
        )
        for order in st.session_state.order_history:
            if str(order["order_id"]) == order_id:
                order["status"] = "CANCELED_DEMO"
                break
        catalog_snapshot = database.catalog_snapshot
        for item in result["items"]:
            product_id = str(item["product_id"])
            catalog_snapshot.loc[
                catalog_snapshot["id"] == product_id,
                "stock",
            ] = int(item["remaining_stock"])
            if not item["still_purchased"]:
                st.session_state.purchased_ids.discard(product_id)
            st.session_state.behavior_weights[product_id] = (
                st.session_state.behavior_weights.get(product_id, 0) - 8.0
            )
        st.session_state.behavior_summary["PURCHASE_CANCEL"] = (
            st.session_state.behavior_summary.get("PURCHASE_CANCEL", 0)
            + len(result["items"])
        )
        clear_order_caches()
        if (
            st.session_state.get("last_order")
            and st.session_state.last_order.get("order_id") == order_id
        ):
            st.session_state.last_order = None
        st.session_state.order_action_notice = (
            f"{order_id} 주문을 취소하고 재고를 복원했습니다."
        )
    except ValueError as error:
        st.session_state.order_action_error = str(error)


def request_demo_order_cancel(order_id: str) -> None:
    st.session_state.pending_cancel_order_id = order_id


def dismiss_demo_order_cancel() -> None:
    st.session_state.pop("pending_cancel_order_id", None)


def confirm_demo_order_cancel(order_id: str) -> None:
    cancel_demo_order(order_id)
    if not st.session_state.get("order_action_error"):
        st.session_state.pop("pending_cancel_order_id", None)


def reorder_demo_order(order_id: str) -> None:
    st.session_state.pop("order_action_error", None)
    try:
        wait_for_pending_cart_writes()
        reordered = database.reorder_to_cart(
            int(st.session_state.user_id),
            order_id,
            st.session_state.session_id,
        )
        st.session_state.cart.update(reordered)
        for product_id in reordered:
            st.session_state.behavior_weights[product_id] = (
                st.session_state.behavior_weights.get(product_id, 0) + 5.0
            )
        st.session_state.behavior_summary["CART_ADD"] = (
            st.session_state.behavior_summary.get("CART_ADD", 0)
            + len(reordered)
        )
        clear_order_caches()
        st.session_state.order_action_notice = (
            "현재 재고를 확인해 주문 상품을 장바구니에 다시 담았습니다."
        )
    except ValueError as error:
        st.session_state.order_action_error = str(error)


def delete_current_review(product_id: str) -> None:
    st.session_state.pop("review_error", None)
    try:
        database.delete_product_review(
            int(st.session_state.user_id),
            product_id,
        )
        get_cached_product_reviews.clear()
        st.session_state.review_notice = "후기를 삭제했습니다."
    except ValueError as error:
        st.session_state.review_error = str(error)


def open_product_detail(product_id: str, reason: str | None = None) -> None:
    st.session_state.header_profile_verified = False
    st.session_state.selected_product_id = product_id
    st.session_state.selected_product_reason = reason
    st.session_state.detail_scroll_pending = True
    st.query_params[PRODUCT_ROUTE_PARAM] = product_id
    database.log_behavior_async(
        int(st.session_state.user_id),
        st.session_state.session_id,
        product_id,
        "VIEW",
    )


def close_product_detail() -> None:
    # Streamlit removes widget-owned keys while the isolated detail screen is
    # rendered. Restore edit controls from the canonical profile state rather
    # than allowing empty widget defaults to overwrite the visible profile.
    st.session_state.profile_nickname = st.session_state.nickname
    st.session_state.profile_interests = list(st.session_state.interests)
    st.session_state.profile_budget = tuple(st.session_state.budget)
    st.session_state.header_profile_verified = False
    st.session_state.selected_product_id = None
    st.session_state.selected_product_reason = None
    if PRODUCT_ROUTE_PARAM in st.query_params:
        del st.query_params[PRODUCT_ROUTE_PARAM]


def sync_product_route(valid_product_ids: set[str]) -> None:
    """Mirror URL history into the product-detail session state."""
    routed_product_id = str(
        st.query_params.get(PRODUCT_ROUTE_PARAM, "")
    ).strip()
    selected_product_id = st.session_state.get("selected_product_id")
    if routed_product_id in valid_product_ids:
        if str(selected_product_id or "") != routed_product_id:
            st.session_state.header_profile_verified = False
            st.session_state.selected_product_id = routed_product_id
            st.session_state.selected_product_reason = (
                "공유 링크 또는 브라우저 기록에서 연 상품입니다."
            )
            st.session_state.detail_scroll_pending = True
        return
    if routed_product_id:
        del st.query_params[PRODUCT_ROUTE_PARAM]
    if selected_product_id is not None:
        st.session_state.selected_product_id = None
        st.session_state.selected_product_reason = None
        st.session_state.header_profile_verified = False


def sync_store_tab_query() -> None:
    """Write a tab change to browser history for mobile back navigation."""
    active_label = st.session_state.get(
        "store_tab",
        STORE_TAB_LABELS[0],
    )
    active_slug = STORE_TAB_SLUGS.get(active_label, "shop")
    st.session_state.store_tab_route = active_slug
    if active_slug == "shop":
        if STORE_TAB_ROUTE_PARAM in st.query_params:
            del st.query_params[STORE_TAB_ROUTE_PARAM]
    else:
        st.query_params[STORE_TAB_ROUTE_PARAM] = active_slug


def sync_store_tab_from_route() -> str:
    """Restore the active tab after browser Back, Forward, or swipe."""
    routed_slug = str(
        st.query_params.get(STORE_TAB_ROUTE_PARAM, "shop")
    ).strip()
    if routed_slug not in STORE_TAB_LABEL_BY_SLUG:
        routed_slug = "shop"
        if STORE_TAB_ROUTE_PARAM in st.query_params:
            del st.query_params[STORE_TAB_ROUTE_PARAM]
    if st.session_state.get("store_tab_route") != routed_slug:
        st.session_state.store_tab = STORE_TAB_LABEL_BY_SLUG[routed_slug]
        st.session_state.store_tab_route = routed_slug
    return STORE_TAB_LABEL_BY_SLUG[routed_slug]


def enable_browser_history_reconciliation() -> None:
    """Keep mobile browser history aligned with Streamlit server state."""
    st.iframe(
        """
        <script>
        (() => {
          const parentWindow = window.parent;
          const handlerKey = "__stylepickHistoryPopstateHandler";
          const previousHandler = parentWindow[handlerKey];
          if (previousHandler) {
            parentWindow.removeEventListener("popstate", previousHandler);
          }
          const reconcileHistory = () => {
            parentWindow.setTimeout(() => {
              parentWindow.location.reload();
            }, 0);
          };
          parentWindow[handlerKey] = reconcileHistory;
          parentWindow.addEventListener("popstate", reconcileHistory);
          parentWindow.history.scrollRestoration = "manual";
        })();
        </script>
        """,
        height=1,
        width=1,
        tab_index=-1,
    )


def buy_product_now(product_id: str) -> None:
    st.session_state.pop("detail_order_error", None)
    try:
        wait_for_pending_cart_writes()
        quantity = int(
            st.session_state.get(f"detail_quantity_{product_id}", 1)
        )
        product_rows = products.loc[products["id"] == product_id]
        available_stock = (
            int(product_rows.iloc[0]["stock"])
            if not product_rows.empty
            else 0
        )
        if quantity > 10:
            raise ValueError("최대 구매 수량(10개)을 초과했습니다.")
        if quantity > available_stock:
            raise ValueError(
                f"현재 구매 가능한 최대 수량은 {available_stock}개입니다."
            )
        order = database.create_product_order(
            int(st.session_state.user_id),
            st.session_state.session_id,
            product_id,
            quantity,
        )
        refresh_catalog_stock(order)
        st.session_state.detail_order = order
        st.session_state.order_history = [
            order,
            *st.session_state.get("order_history", []),
        ][:5]
        st.session_state.purchased_ids.add(product_id)
    except ValueError as error:
        st.session_state.detail_order_error = str(error)


def render_product_detail_page(product_id: str) -> None:
    product = products.loc[products["id"] == product_id].iloc[0]
    if st.session_state.pop("detail_scroll_pending", False):
        st.iframe(
            """
            <script>
            (() => {
              const parentWindow = window.parent;
              const parentDocument = parentWindow.document;
              const scrollTargets = [
                parentDocument.scrollingElement,
                parentDocument.querySelector('[data-testid="stAppViewContainer"]'),
                parentDocument.querySelector('[data-testid="stMain"]'),
                parentDocument.querySelector('.stMain'),
                parentDocument.querySelector('section.main')
              ].filter(Boolean);
              const moveToTop = () => {
                parentWindow.scrollTo({ top: 0, left: 0, behavior: "auto" });
                parentDocument.documentElement.scrollTop = 0;
                parentDocument.body.scrollTop = 0;
                scrollTargets.forEach((target) => {
                  target.scrollTo({ top: 0, left: 0, behavior: "auto" });
                });
                parentDocument.querySelectorAll("*").forEach((target) => {
                  const style = parentWindow.getComputedStyle(target);
                  if (
                    target.scrollHeight > target.clientHeight &&
                    ["auto", "scroll"].includes(style.overflowY)
                  ) {
                    target.scrollTop = 0;
                  }
                });
              };
              moveToTop();
              parentWindow.requestAnimationFrame(moveToTop);
              [60, 160, 320].forEach((delay) => {
                parentWindow.setTimeout(moveToTop, delay);
              });
            })();
            </script>
            """,
            height=1,
            width=1,
            tab_index=-1,
        )
    st.markdown(
        '<div class="detail-page-marker" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="detail_back_bar"):
        st.button(
            "← 쇼핑으로 돌아가기",
            key="detail_back",
            on_click=close_product_detail,
        )
    visual_col, info_col = st.columns([1, 1.15], gap="large")
    with visual_col:
        st.markdown(
            f"""
            <div class="product-card detail-product-visual">
              <div class="detail-product-emoji">{product['emoji']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with info_col:
        st.markdown(
            '<div class="detail-info-marker" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"{product['brand']} · {product['category']} · ⭐ {product['rating']}"
        )
        st.markdown(
            f'<h1 class="detail-product-title">{escape(str(product["name"]))}</h1>',
            unsafe_allow_html=True,
        )
        st.write(product["description"])
        if reason := st.session_state.get("selected_product_reason"):
            st.success(f"✨ {reason}")
        st.markdown(f"**상품 태그** · {product['tags']}")
        price_col, stock_col = st.columns(2)
        price_col.metric("판매가", f"{int(product['price']):,}원")
        stock_col.metric("현재 재고", f"{int(product['stock'])}개")
        available_stock = int(product["stock"])
        quantity_key = f"detail_quantity_{product_id}"
        if available_stock > 0:
            maximum_quantity = min(10, available_stock)
            selected_quantity = min(
                maximum_quantity,
                max(1, int(st.session_state.get(quantity_key, 1))),
            )
            if quantity_key in st.session_state:
                st.session_state[quantity_key] = selected_quantity
            st.number_input(
                "구매 수량",
                min_value=1,
                max_value=maximum_quantity,
                value=selected_quantity,
                key=quantity_key,
            )
        else:
            st.session_state.pop(quantity_key, None)
            st.warning("현재 재고가 모두 소진되었습니다.")

    favorite_label = (
        "찜 해제" if product_id in st.session_state.favorites else "♡ 찜하기"
    )
    favorite_col, cart_col, buy_col = st.columns(3)
    favorite_col.button(
        favorite_label,
        key=f"detail_favorite_{product_id}",
        width="stretch",
        on_click=toggle_favorite,
        args=(product_id,),
    )
    cart_col.button(
        "품절" if int(product["stock"]) <= 0 else "장바구니 담기",
        key=f"detail_cart_{product_id}",
        type="primary",
        width="stretch",
        disabled=int(product["stock"]) <= 0,
        on_click=add_to_cart,
        args=(product_id,),
    )
    buy_col.button(
        "바로 모의결제",
        key=f"detail_buy_{product_id}",
        width="stretch",
        disabled=int(product["stock"]) <= 0,
        on_click=buy_product_now,
        args=(product_id,),
    )
    if detail_order := st.session_state.get("detail_order"):
        st.success(
            f"모의 주문 {detail_order['order_id']} 완료 · "
            f"{detail_order['total']:,}원"
        )
    if detail_error := st.session_state.get("detail_order_error"):
        st.error(detail_error)

    reviews = get_cached_product_reviews(
        DATABASE_TARGET,
        product_id,
        database,
    )
    review_count = len(reviews)
    review_average = (
        sum(review["rating"] for review in reviews) / review_count
        if review_count
        else 0
    )
    with st.expander(
        f"구매자 후기 · {review_count}개"
        + (f" · ⭐ {review_average:.1f}" if review_count else "")
    ):
        if review_notice := st.session_state.pop("review_notice", None):
            st.success(review_notice)
        if review_error := st.session_state.get("review_error"):
            st.error(review_error)

        current_review = next(
            (
                review
                for review in reviews
                if int(review["user_id"]) == int(st.session_state.user_id)
            ),
            None,
        )
        if product_id in st.session_state.purchased_ids:
            st.caption("구매 확인 완료 · 상품별 후기 1개를 작성·수정할 수 있습니다.")
            with st.form(f"review_form_{product_id}"):
                rating = st.select_slider(
                    "별점",
                    options=[1, 2, 3, 4, 5],
                    value=(
                        int(current_review["rating"])
                        if current_review
                        else 5
                    ),
                    format_func=lambda value: f"{value}점",
                )
                content = st.text_area(
                    "후기",
                    value=(
                        str(current_review["content"])
                        if current_review
                        else ""
                    ),
                    placeholder="상품을 직접 사용한 경험을 5자 이상 작성해 주세요.",
                    max_chars=500,
                )
                review_submitted = st.form_submit_button(
                    "후기 수정" if current_review else "후기 등록",
                    type="primary",
                    width="stretch",
                )
            if review_submitted:
                try:
                    database.save_product_review(
                        int(st.session_state.user_id),
                        product_id,
                        int(rating),
                        content,
                    )
                    get_cached_product_reviews.clear()
                    st.session_state.pop("review_error", None)
                    st.session_state.review_notice = "후기가 저장되었습니다."
                    st.rerun()
                except ValueError as error:
                    st.session_state.review_error = str(error)
                    st.rerun()
            if current_review:
                st.button(
                    "내 후기 삭제",
                    key=f"delete_review_{product_id}",
                    width="stretch",
                    on_click=delete_current_review,
                    args=(product_id,),
                )
        else:
            st.caption("구매 완료한 회원만 후기를 작성할 수 있습니다.")

        if not reviews:
            st.info("아직 등록된 구매자 후기가 없습니다.")
        else:
            st.divider()
            for index, review in enumerate(reviews):
                if index:
                    st.divider()
                stars = "★" * int(review["rating"]) + "☆" * (
                    5 - int(review["rating"])
                )
                st.markdown(
                    f"**{escape(str(review['nickname']))}** · {stars}"
                )
                st.write(review["content"])
                st.caption(f"구매 확인 · {review['updated_at']}")


def product_card(product: pd.Series, key_prefix: str, reason: str | None = None) -> None:
    description = escape(str(product["description"]))
    reason_html = (
        f"<div class='reason'>✨ {escape(reason)}</div>" if reason else ""
    )
    st.markdown(
        f"""
        <div class="product-card">
          <div class="product-visual">
            <div class="product-emoji">{product['emoji']}</div>
          </div>
          <div class="product-category">{escape(str(product['category']))}</div>
          <div class="product-brand">{escape(str(product['brand']))}</div>
          <div class="product-name">{escape(str(product['name']))}</div>
          <div class="product-description">{description}</div>
          <div class="product-meta">
            <b>{int(product['price']):,}원</b><span>⭐ {product['rating']}</span>
          </div>
          <div style="color:#64748b;font-size:.8rem;margin-top:.4rem">
            {"품절" if int(product["stock"]) <= 0 else f"재고 {int(product['stock'])}개"}
          </div>
          {reason_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    detail_col, favorite_col, cart_col = st.columns([1, 1, 1])
    detail_col.button(
        "상세",
        key=f"{key_prefix}_detail_{product['id']}",
        width="stretch",
        on_click=open_product_detail,
        args=(str(product["id"]), reason),
    )
    favorite_icon = "♥" if product["id"] in st.session_state.favorites else "♡"
    favorite_col.button(
        favorite_icon,
        key=f"{key_prefix}_favorite_{product['id']}",
        width="stretch",
        on_click=toggle_favorite,
        args=(str(product["id"]),),
    )
    cart_col.button(
        "품절" if int(product["stock"]) <= 0 else "담기",
        key=f"{key_prefix}_cart_{product['id']}",
        type="primary",
        width="stretch",
        disabled=int(product["stock"]) <= 0,
        on_click=add_to_cart,
        args=(str(product["id"]),),
    )


def product_grid(
    frame: pd.DataFrame,
    key_prefix: str,
    show_reasons: bool = False,
    columns_per_row: int = 3,
) -> None:
    if frame.empty:
        st.info("조건에 맞는 상품이 없습니다.")
        return
    rows = frame.reset_index(drop=True)
    for start in range(0, len(rows), columns_per_row):
        columns = st.columns(columns_per_row)
        for offset, container in enumerate(columns):
            index = start + offset
            if index >= len(rows):
                continue
            with container:
                item = rows.iloc[index]
                reason = (
                    str(item["recommendation_reason"])
                    if show_reasons
                    else None
                )
                product_card(item, key_prefix, reason)


def section_heading(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="section-heading">
          <span class="section-kicker">{escape(kicker)}</span>
          <h2>{escape(title)}</h2>
          <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Load the local catalog and TextCNN in a background thread. The main thread only
# reads inexpensive file metadata before rendering authentication.
catalog_stat = PRODUCT_PATH.stat()
catalog_fingerprint = (
    catalog_stat.st_mtime_ns,
    catalog_stat.st_size,
)
if os.environ.get("STYLEPICK_TEST_SYNC_STARTUP") == "1":
    model_future = Future()
    model_future.set_result(
        get_recommendation_model_sync(
            RECOMMENDER_BACKEND,
            catalog_fingerprint,
        )
    )
else:
    model_future = get_recommendation_model_future(
        RECOMMENDER_BACKEND,
        catalog_fingerprint,
    )

initialize_auth()
render_auth_cookie_action()
if (
    not st.session_state.user_id
    and st.session_state.get("auth_restore_error")
):
    with auth_page_slot.container():
        st.error(
            "로그인 정보를 불러오는 중 데이터베이스 연결이 잠시 끊겼습니다. "
            "아래 버튼을 눌러 다시 시도해 주세요.",
            icon="🛠️",
        )
        st.button("다시 연결", type="primary", width="stretch")
    st.stop()
if not st.session_state.user_id:
    should_probe_cookie = should_probe_browser_cookie(
        AUTH_COOKIE_COMPONENT_ENABLED,
        bool(st.session_state.get("auth_cookie_probe_started")),
        bool(st.session_state.get("auth_cookie_restore_blocked")),
    )
    with auth_page_slot.container():
        if should_probe_cookie:
            st.session_state.auth_cookie_probe_started = True
            render_auth_probe()
        else:
            render_auth()
    st.stop()
auth_page_slot.markdown(
    """
    <div style="
      max-width:520px;margin:12vh auto;padding:1.4rem 1.6rem;
      border:1px solid #e5e7eb;border-radius:20px;background:#fff;
      box-shadow:0 18px 50px rgba(15,23,42,.08);text-align:center
    ">
      <b style="font-size:1.08rem">로그인 완료</b>
      <div style="margin-top:.35rem;color:#64748b">
        취향과 상품 정보를 불러오고 있어요.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    database = database_future.result()
except RuntimeError as error:
    if not is_database_unavailable_error(error):
        raise
    logging.exception("StylePick database is unavailable during initialization")
    prepare_database_retry()
    st.warning(DATABASE_RECOVERY_MESSAGE, icon="⏳")
    st.caption("이 화면은 약 5초 후 자동으로 새로고침됩니다.")
    time.sleep(5)
    st.rerun()
except Exception:
    if os.environ.get("APP_ENV", "development").lower() == "production":
        logging.exception("StylePick database initialization failed")
        st.error(
            "서비스 데이터베이스에 연결하지 못했습니다. "
            "잠시 후 다시 시도해 주세요.",
            icon="🛠️",
        )
        st.stop()
    raise

products = get_database_products(DATABASE_TARGET, database)
CATEGORIES = sorted(products["category"].unique().tolist())
MAX_PRICE = int(products["price"].max())
model = model_future.result()
active_user_id = int(st.session_state.user_id)
if st.session_state.get("loaded_user_id") != active_user_id:
    storefront_snapshot = st.session_state.pop(
        "storefront_snapshot_ready",
        None,
    )
    if storefront_snapshot is None:
        storefront_snapshot = get_storefront_snapshot(
            DATABASE_TARGET,
            active_user_id,
            database,
        )
    initialize_state(storefront_snapshot)
auth_page_slot.empty()
current_user = st.session_state.get("current_user")
if current_user is None:
    current_user = get_cached_user(
        DATABASE_TARGET,
        int(st.session_state.user_id),
        database,
    )
    st.session_state.current_user = current_user
behavior_summary = st.session_state.behavior_summary
if auth_notice := st.session_state.pop("auth_notice", None):
    st.toast(auth_notice, icon="✅")
enable_browser_history_reconciliation()
sync_product_route(set(products["id"].astype(str)))

with st.sidebar:
    st.caption(f"로그인: {current_user['email']}")
    st.header(f"👤 {st.session_state.nickname}님")
    st.subheader("AI 추천 취향")
    st.caption("저장한 값은 AI 추천에 계속 반영되며 상품 탐색 필터와는 별개입니다.")
    with st.form("sidebar_preference_form"):
        st.multiselect(
            "관심 카테고리 (AI 추천)",
            CATEGORIES,
            max_selections=3,
            key="profile_interests",
        )
        st.slider(
            "관심 가격대 (AI 추천)",
            min_value=0,
            max_value=MAX_PRICE,
            step=5_000,
            format="%d원",
            key="profile_budget",
        )
        st.form_submit_button(
            "추천 취향 저장",
            type="primary",
            width="stretch",
            on_click=save_profile_settings,
        )
    if st.session_state.pop("profile_saved_notice", False):
        st.success("AI 추천 취향을 저장했습니다.")
    if profile_error := st.session_state.get("profile_error"):
        st.error(profile_error)
    st.caption(
        "닉네임·전화번호·비밀번호 수정과 계정 관리는 "
        "화면 상단의 프로필 버튼에서 할 수 있습니다."
    )
    st.divider()
    sidebar_orders = st.session_state.get("order_history", [])
    with st.expander(f"결제 내역 · {len(sidebar_orders)}건"):
        if not sidebar_orders:
            st.caption("아직 모의결제 내역이 없습니다.")
        else:
            for index, order in enumerate(sidebar_orders[:5]):
                if index:
                    st.divider()
                st.markdown(f"**{int(order['total']):,}원**")
                st.caption(
                    f"{order['ordered_at']} · "
                    f"총 {int(order['quantity'])}개 · "
                    f"{order_status_label(order['status'])}"
                )
                item_names = ", ".join(
                    str(item["name"])
                    for item in order.get("items", [])
                )
                if item_names:
                    st.caption(item_names)
                st.caption(f"주문번호 · {order['order_id']}")
                order_id = str(order["order_id"])
                status = str(order["status"])
                if status == "CANCELED_DEMO":
                    st.button(
                        "주문 취소 완료",
                        key=f"sidebar_cancel_complete_{order_id}",
                        width="stretch",
                        disabled=True,
                    )
                elif status != "PAID_DEMO":
                    st.button(
                        "주문 취소 불가",
                        key=f"sidebar_cancel_unavailable_{order_id}",
                        width="stretch",
                        disabled=True,
                    )
                elif (
                    st.session_state.get("pending_cancel_order_id")
                    == order_id
                ):
                    st.warning("이 주문을 취소하시겠습니까?")
                    confirm_col, back_col = st.columns(2)
                    confirm_col.button(
                        "취소 확정",
                        key=f"sidebar_confirm_cancel_{order_id}",
                        type="primary",
                        width="stretch",
                        on_click=confirm_demo_order_cancel,
                        args=(order_id,),
                    )
                    back_col.button(
                        "돌아가기",
                        key=f"sidebar_dismiss_cancel_{order_id}",
                        width="stretch",
                        on_click=dismiss_demo_order_cancel,
                    )
                else:
                    st.button(
                        "주문 취소",
                        key=f"sidebar_cancel_order_{order_id}",
                        width="stretch",
                        on_click=request_demo_order_cancel,
                        args=(order_id,),
                    )
            st.caption("최근 모의결제 5건까지 표시됩니다.")
    st.caption(
        f"개인화 행동 {sum(behavior_summary.values()):,}건이 추천에 반영됩니다."
    )
    st.button("로그아웃", width="stretch", on_click=logout_user)

if selected_product_id := st.session_state.get("selected_product_id"):
    render_product_detail_page(str(selected_product_id))
    st.stop()

behavior_weights = st.session_state.behavior_weights
trend_scores = st.session_state.trend_scores
purchased_ids = st.session_state.purchased_ids
budget_min, budget_max = st.session_state.budget
base_recommendations = rank_products(
    products=products,
    model=model,
    interests=list(st.session_state.interests),
    favorite_ids=set(st.session_state.favorites),
    budget_min=budget_min,
    budget_max=budget_max,
    top_n=24,
    behavior_product_weights=behavior_weights,
    trend_product_scores=trend_scores,
    purchased_ids=purchased_ids,
)

st.markdown('<div class="store-shell-marker"></div>', unsafe_allow_html=True)
with st.container(key="store_header"):
    brand_col, profile_col, favorite_col, cart_col = st.columns(
        [4, 1.35, .75, .75],
        vertical_alignment="center",
    )
    brand_col.markdown(
        """
        <div class="brand-lockup">
          <div class="brand-mark">SP</div>
          <div>
            <div class="brand-name">StylePick AI</div>
            <div class="brand-caption">나를 이해하는 설명 가능한 쇼핑</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with profile_col.popover(
        f"👤 {st.session_state.nickname}님",
        width="stretch",
    ):
        st.caption(f"계정 · {current_user['email']}")
        if profile_notice := st.session_state.pop(
            "header_profile_notice",
            None,
        ):
            st.success(profile_notice)
        if profile_error := st.session_state.get("header_profile_error"):
            st.error(profile_error)
        if not st.session_state.get("header_profile_verified", False):
            st.write("정보를 수정하려면 현재 비밀번호를 확인해 주세요.")
            with st.form("header_profile_verify_form"):
                st.text_input(
                    "현재 비밀번호",
                    type="password",
                    key="header_profile_password",
                )
                st.form_submit_button(
                    "비밀번호 확인",
                    type="primary",
                    width="stretch",
                    on_click=verify_header_profile_password,
                )
        else:
            with st.form("header_account_edit_form"):
                st.text_input("닉네임", key="header_profile_nickname")
                st.text_input(
                    "전화번호",
                    key="header_profile_phone",
                    max_chars=20,
                )
                st.text_input(
                    "새 비밀번호",
                    type="password",
                    key="header_new_password",
                    help="변경하지 않으려면 비워 두세요.",
                )
                st.text_input(
                    "새 비밀번호 확인",
                    type="password",
                    key="header_confirm_password",
                )
                st.form_submit_button(
                    "계정 정보 저장",
                    type="primary",
                    width="stretch",
                    on_click=save_header_account_settings,
                )
        st.divider()
        st.caption("계정 관리")
        with st.expander("회원탈퇴"):
            st.warning(
                "탈퇴하면 계정, 취향, 찜, 장바구니, 행동 및 주문 "
                "데이터가 즉시 삭제됩니다."
            )
            with st.form("delete_account_form"):
                st.text_input(
                    "현재 비밀번호",
                    type="password",
                    key="delete_account_password",
                )
                delete_confirmed = st.checkbox(
                    "삭제된 데이터는 복구할 수 없음을 확인했습니다."
                )
                st.form_submit_button(
                    "계정 영구 삭제",
                    disabled=not delete_confirmed,
                    width="stretch",
                    on_click=delete_current_user,
                )
                if delete_error := st.session_state.get(
                    "delete_account_error"
                ):
                    st.error(delete_error)

    with favorite_col.popover(
        f"♥ {len(st.session_state.favorites)}",
        width="stretch",
    ):
        st.subheader("찜한 상품")
        header_favorites = products[
            products["id"].isin(st.session_state.favorites)
        ]
        if header_favorites.empty:
            st.caption("찜한 상품이 없습니다.")
        for _, item in header_favorites.iterrows():
            st.markdown(f"{item['emoji']} **{item['name']}**")
            st.caption(
                f"{int(item['price']):,}원 · 재고 {int(item['stock'])}개"
            )
            st.button(
                "구매 화면",
                key=f"header_favorite_detail_{item['id']}",
                width="stretch",
                on_click=open_product_detail,
                args=(str(item["id"]), "찜한 상품에서 선택한 상품입니다."),
            )
            st.divider()

    with cart_col.popover(
        f"🛒 {sum(st.session_state.cart.values())}",
        width="stretch",
    ):
        st.subheader("장바구니")
        header_cart = products[products["id"].isin(st.session_state.cart)]
        if header_cart.empty:
            st.caption("장바구니가 비어 있습니다.")
        else:
            header_cart_total = 0
            for _, item in header_cart.iterrows():
                quantity = int(st.session_state.cart[str(item["id"])])
                line_total = int(item["price"]) * quantity
                header_cart_total += line_total
                st.markdown(f"{item['emoji']} **{item['name']}**")
                st.caption(f"{quantity}개 · {line_total:,}원")
                st.divider()
            st.markdown(f"**합계 {header_cart_total:,}원**")
            st.button(
                "장바구니 모의결제",
                key="header_cart_checkout",
                type="primary",
                width="stretch",
                on_click=complete_order,
            )
            st.caption("포트폴리오 시연용이며 실제 결제는 발생하지 않습니다.")

if checkout_notice := st.session_state.pop("checkout_notice", None):
    st.toast(checkout_notice, icon="✅")
if checkout_error := st.session_state.pop("checkout_error", None):
    st.error(checkout_error, icon="⚠️")

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-copy">
        <span class="hero-eyebrow">PERSONAL SHOPPING, EXPLAINED</span>
        <h1>취향을 발견하는<br>가장 똑똑한 쇼핑.</h1>
        <p>
          {escape(st.session_state.nickname)}님의 관심사와 최근 행동을 바탕으로
          20·30대 라이프스타일 상품을 고르고 추천 이유까지 알려드려요.
        </p>
        <div class="hero-tags">
          <span class="hero-tag">✨ 자연어 추천</span>
          <span class="hero-tag">🎯 행동 기반 개인화</span>
          <span class="hero-tag">🔎 추천 이유 제공</span>
        </div>
      </div>
      <div class="hero-summary">
        <div class="hero-stat"><b>{len(products)}</b><span>엄선된 상품</span></div>
        <div class="hero-stat"><b>{len(CATEGORIES)}</b><span>라이프 카테고리</span></div>
        <div class="hero-stat"><b>{sum(behavior_summary.values())}</b><span>반영된 나의 행동</span></div>
        <div class="hero-stat"><b>{RECOMMENDER_BACKEND.upper()}</b><span>추천 모델</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

default_store_tab = sync_store_tab_from_route()
shop_tab, recommend_tab, favorite_tab, cart_tab = st.tabs(
    STORE_TAB_LABELS,
    default=default_store_tab,
    key="store_tab",
    on_change=sync_store_tab_query,
)

with shop_tab:
    section_heading(
        "FOR YOU",
        f"{st.session_state.nickname}님, 이런 상품은 어때요?",
        "저장한 취향과 최근 행동을 반영해 먼저 보여드리는 AI 추천입니다.",
    )
    product_grid(
        base_recommendations.head(4),
        "home_personal",
        show_reasons=True,
        columns_per_row=4,
    )
    section_heading(
        "DISCOVER",
        "모든 상품 둘러보기",
        "검색과 필터로 지금 필요한 상품을 빠르게 찾아보세요.",
    )
    search_col, category_col, sort_col = st.columns([1.4, 1, 0.9])
    query = search_col.text_input(
        "상품 검색",
        placeholder="상품명이나 설명을 검색하세요",
    )
    if (
        query.strip()
        and query.strip() != st.session_state.get("last_logged_search")
    ):
        database.log_behavior(
            int(st.session_state.user_id),
            st.session_state.session_id,
            None,
            "SEARCH",
            search_keyword=query.strip()[:100],
        )
        st.session_state.last_logged_search = query.strip()
    selected_categories = category_col.multiselect(
        "카테고리 필터",
        CATEGORIES,
    )
    sort_option = sort_col.selectbox(
        "정렬",
        ["인기순", "평점순", "낮은 가격순", "높은 가격순"],
    )
    price_range = st.slider(
        "가격 필터",
        min_value=0,
        max_value=MAX_PRICE,
        value=(0, MAX_PRICE),
        step=5_000,
        format="%d원",
    )
    filtered = products[
        products["price"].between(price_range[0], price_range[1])
    ]
    if selected_categories:
        filtered = filtered[filtered["category"].isin(selected_categories)]
    if query.strip():
        searchable = (
            filtered["name"]
            + " "
            + filtered["category"]
            + " "
            + filtered["description"]
        )
        filtered = filtered[
            searchable.str.contains(query.strip(), case=False, regex=False)
        ]
    sort_rules = {
        "인기순": ("popularity", False),
        "평점순": ("rating", False),
        "낮은 가격순": ("price", True),
        "높은 가격순": ("price", False),
    }
    sort_column, ascending = sort_rules[sort_option]
    filtered = filtered.sort_values(sort_column, ascending=ascending)
    st.caption(f"{len(filtered)}개 상품")
    catalog_page_size = 9
    catalog_page_count = max(
        1,
        (len(filtered) + catalog_page_size - 1) // catalog_page_size,
    )
    catalog_filter_key = (
        query.strip().casefold(),
        tuple(sorted(selected_categories)),
        tuple(price_range),
        sort_option,
    )
    catalog_page = st.selectbox(
        "상품 페이지",
        options=list(range(catalog_page_count)),
        format_func=lambda page: f"{page + 1} / {catalog_page_count} 페이지",
        key=f"catalog_page_{hash(catalog_filter_key)}",
    )
    catalog_start = int(catalog_page) * catalog_page_size
    product_grid(
        filtered.iloc[catalog_start:catalog_start + catalog_page_size],
        f"shop_page_{catalog_page}",
    )

with recommend_tab:
    section_heading(
        "AI CURATION",
        f"{st.session_state.nickname}님만을 위한 추천 피드",
        "자연어로 원하는 상황을 말하면 의미와 행동을 함께 분석해 진열대를 다시 구성합니다.",
    )
    recommendation_query = st.text_input(
        "원하는 상품을 자연어로 입력하세요",
        placeholder="예: 비 오는 날 가볍게 달릴 때 입을 옷",
        key="recommendation_query",
    )
    recommendations = rank_products(
        products=products,
        model=model,
        interests=list(st.session_state.interests),
        favorite_ids=set(st.session_state.favorites),
        budget_min=budget_min,
        budget_max=budget_max,
        top_n=24,
        behavior_product_weights=behavior_weights,
        trend_product_scores=trend_scores,
        purchased_ids=purchased_ids,
        query_text=recommendation_query,
    )
    if (
        not recommendation_query.strip()
        and not st.session_state.interests
        and not st.session_state.favorites
        and not behavior_weights
    ):
        st.info(
            "아직 취향 정보가 없어 예산 범위와 인기도를 이용한 콜드 스타트 추천입니다. "
            "관심 카테고리를 저장하거나 상품을 찜하면 개인화됩니다."
        )
    elif st.session_state.interests:
        selected_interest_labels = ", ".join(st.session_state.interests)
        st.success(
            f"선택한 관심 카테고리({selected_interest_labels}) 안에서 "
            "CNN이 개인별 추천 순서를 계산했습니다."
        )
    else:
        st.success(
            "관심사와 최근 클릭·찜·장바구니·구매 행동을 반영한 회원별 추천입니다."
        )
    with st.expander("추천 점수는 어떻게 계산되나요?"):
        st.code(
            "1단계 후보 검색 = TextCNN 취향 유사도 + TextCNN 행동 유사도\n"
            "2단계 최종 랭킹 = CNN 콘텐츠×0.30 + 카테고리×0.20\n"
            "                 + CNN 행동×0.20 + 예산×0.10\n"
            "                 + 최근 트렌드×0.10 + 평점×0.10\n"
            "                 - 부정 행동 패널티"
        )
        st.write(
            "일반적인 이커머스 추천처럼 후보 검색과 최종 랭킹을 분리했습니다. "
            "TextCNN이 상품명·카테고리·설명·태그의 의미 특징을 학습해 관련 후보를 먼저 찾고, "
            "후보 안에서 사용자별 취향·최근 행동과 쇼핑 조건을 결합해 최종 순서를 결정합니다. "
            "행동은 클릭 1, 찜 4, 장바구니 5, 구매 8점이며 최근 행동을 더 크게 반영합니다. "
            "찜·장바구니에서 제거한 상품은 추천 점수가 낮아집니다."
        )
        st.caption(
            f"2단계 하이브리드 · 후보 모델 {RECOMMENDER_BACKEND.upper()} · "
            f"현재 반영된 행동 상품 {len(behavior_weights)}개 · "
            f"최근 7일 트렌드 상품 {len(trend_scores)}개 · "
            f"구매 완료 제외 상품 {len(purchased_ids)}개"
        )
    recommendation_modules = [
        (
            "TOP PICKS",
            "이 추천은 놓치지 마세요",
            "AI 종합 점수가 가장 높은 취향 맞춤 상품입니다.",
            recommendations.iloc[0:4],
            "recommend_top",
        ),
        (
            "BEHAVIOR MATCH",
            "최근 관심과 이어지는 상품",
            (
                "최근 조회·찜·장바구니 행동과 의미가 가까운 상품입니다."
                if behavior_weights
                else "첫 방문 취향과 예산을 바탕으로 고른 상품입니다."
            ),
            recommendations.iloc[4:8],
            "recommend_behavior",
        ),
        (
            "TREND NOW",
            "지금 함께 살펴볼 인기 상품",
            "최근 트렌드, 평점, 개인화 적합도를 함께 반영했습니다.",
            recommendations.iloc[8:12],
            "recommend_trend",
        ),
        (
            "NEW DISCOVERY",
            "새로운 취향을 발견해 보세요",
            "같은 카테고리만 반복되지 않도록 다양성을 고려한 추천입니다.",
            recommendations.iloc[12:16],
            "recommend_discovery",
        ),
    ]
    available_modules = [
        module
        for module in recommendation_modules
        if not module[3].empty
    ]
    selected_module_index = st.selectbox(
        "추천 테마",
        options=list(range(len(available_modules))),
        format_func=lambda index: available_modules[index][1],
    )
    kicker, title, description, module, key = available_modules[
        int(selected_module_index)
    ]
    section_heading(kicker, title, description)
    product_grid(
        module,
        key,
        show_reasons=True,
        columns_per_row=4,
    )

with favorite_tab:
    st.subheader("관심 상품")
    favorites = products[products["id"].isin(st.session_state.favorites)]
    if favorites.empty:
        st.info("찜한 상품이 없습니다. 상품을 찜하면 AI 추천에도 반영됩니다.")
    product_grid(favorites, "favorites")

with cart_tab:
    st.subheader("장바구니")
    if st.session_state.last_order:
        order = st.session_state.last_order
        st.success("모의 주문이 완료되었습니다!")
        order_col1, order_col2, order_col3 = st.columns(3)
        order_col1.metric("주문 번호", order["order_id"])
        order_col2.metric("결제 금액", f"{order['total']:,}원")
        order_col3.metric("상품 수량", order["quantity"])
        st.caption(f"주문 시각: {order['ordered_at']} · 실제 결제는 발생하지 않았습니다.")
        st.button("새 쇼핑 계속하기", on_click=reset_last_order)

    cart_items = products[products["id"].isin(st.session_state.cart)]
    if cart_items.empty and not st.session_state.last_order:
        st.info("장바구니가 비어 있습니다.")
    elif not cart_items.empty:
        total = 0
        for _, item in cart_items.iterrows():
            product_id = str(item["id"])
            item_col, quantity_col, price_col, delete_col = st.columns(
                [3, 1.2, 1.3, 0.8]
            )
            item_col.write(f"{item['emoji']} **{item['name']}**")
            available = min(10, int(item["stock"]))
            if available <= 0:
                quantity_col.error("품절")
                price_col.write("-")
                delete_col.button(
                    "삭제",
                    key=f"delete_soldout_{product_id}",
                    on_click=remove_from_cart,
                    args=(product_id,),
                )
                continue
            current_quantity = min(
                int(st.session_state.cart[product_id]),
                available,
            )
            quantity = quantity_col.number_input(
                "수량",
                min_value=1,
                max_value=available,
                value=current_quantity,
                key=f"quantity_{product_id}",
                label_visibility="collapsed",
            )
            if int(quantity) != int(st.session_state.cart[product_id]):
                st.session_state.cart[product_id] = int(quantity)
                pending_writes = [
                    pending_write
                    for pending_write in st.session_state.get(
                        "pending_cart_writes",
                        [],
                    )
                    if not pending_write.done()
                ]
                pending_writes.append(
                    database.set_cart_quantity_async(
                        int(st.session_state.user_id),
                        product_id,
                        int(quantity),
                    )
                )
                st.session_state.pending_cart_writes = pending_writes
            line_total = int(item["price"]) * int(quantity)
            total += line_total
            price_col.write(f"**{line_total:,}원**")
            delete_col.button(
                "삭제",
                key=f"delete_{product_id}",
                on_click=remove_from_cart,
                args=(product_id,),
            )
            st.divider()

        summary_col, checkout_col = st.columns([2, 1])
        summary_col.metric("모의 결제 합계", f"{total:,}원")
        summary_col.caption("최종 금액과 재고는 주문 시 서버에서 다시 검증합니다.")
        checkout_col.button(
            "모의 주문 완료",
            type="primary",
            width="stretch",
            on_click=complete_order,
        )
    order_history = st.session_state.order_history
    if order_notice := st.session_state.pop("order_action_notice", None):
        st.success(order_notice)
    if order_error := st.session_state.get("order_action_error"):
        st.error(order_error)
    if order_history:
        st.subheader("주문 관리")
        for order in order_history:
            status = str(order["status"])
            status_label = order_status_label(status)
            with st.expander(
                f"{status_label} · {order['order_id']} · "
                f"{int(order['total']):,}원"
            ):
                st.caption(
                    f"주문 시각 {order['ordered_at']} · "
                    f"총 {int(order['quantity'])}개"
                )
                for item in order["items"]:
                    item_total = (
                        int(item["unit_price"]) * int(item["quantity"])
                    )
                    st.write(
                        f"**{item['name']}** · {int(item['quantity'])}개 · "
                        f"{item_total:,}원"
                    )
                if status == "CANCELED_DEMO":
                    st.info("취소가 완료되어 구매 수량만큼 재고가 복원됐습니다.")
                cancel_col, reorder_col = st.columns(2)
                order_id = str(order["order_id"])
                if status == "CANCELED_DEMO":
                    cancel_col.button(
                        "주문 취소 완료",
                        key=f"cancel_complete_{order_id}",
                        disabled=True,
                        width="stretch",
                    )
                elif status != "PAID_DEMO":
                    cancel_col.button(
                        "주문 취소 불가",
                        key=f"cancel_unavailable_{order_id}",
                        disabled=True,
                        width="stretch",
                    )
                elif (
                    st.session_state.get("pending_cancel_order_id")
                    == order_id
                ):
                    with cancel_col:
                        st.warning("주문을 취소하시겠습니까?")
                        confirm_col, dismiss_col = st.columns(2)
                        confirm_col.button(
                            "취소 확정",
                            key=f"confirm_cancel_{order_id}",
                            type="primary",
                            width="stretch",
                            on_click=confirm_demo_order_cancel,
                            args=(order_id,),
                        )
                        dismiss_col.button(
                            "돌아가기",
                            key=f"dismiss_cancel_{order_id}",
                            width="stretch",
                            on_click=dismiss_demo_order_cancel,
                        )
                else:
                    cancel_col.button(
                        "주문 취소",
                        key=f"cancel_order_{order_id}",
                        width="stretch",
                        on_click=request_demo_order_cancel,
                        args=(order_id,),
                    )
                reorder_col.button(
                    "다시 담기",
                    key=f"reorder_{order_id}",
                    width="stretch",
                    on_click=reorder_demo_order,
                    args=(order_id,),
                )

st.markdown(
    """
    <section class="trust-strip">
      <div class="trust-item">
        <b>🔒 안전한 계정 정보</b>
        <span>비밀번호는 평문이 아닌 PBKDF2 해시로 MySQL에 저장됩니다.</span>
      </div>
      <div class="trust-item">
        <b>✨ 설명 가능한 추천</b>
        <span>검색과 행동을 반영한 이유를 상품마다 투명하게 안내합니다.</span>
      </div>
      <div class="trust-item">
        <b>↩️ 안심 데모 쇼핑</b>
        <span>현재 주문은 포트폴리오 시연용이며 실제 결제는 발생하지 않습니다.</span>
      </div>
    </section>
    <footer class="store-footer">
      <div><b>StylePick AI</b><br>20·30대 라이프스타일을 위한 AI 커머스 데모</div>
      <div>배송·교환·반품 안내 · FAQ · 고객지원 · 개인정보처리방침 · 이용약관</div>
    </footer>
    """,
    unsafe_allow_html=True,
)
