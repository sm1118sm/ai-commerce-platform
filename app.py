"""StylePick AI: a three-day-hackathon personalized commerce MVP."""

from __future__ import annotations

from concurrent.futures import Future
from html import escape
import logging
import os
from pathlib import Path
from threading import Thread, Timer
from typing import TYPE_CHECKING
from uuid import uuid4

import streamlit as st

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
      .block-container {
        max-width: 1280px;
        padding-top: 1.25rem;
        padding-bottom: 6rem;
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
      .brand-lockup { display: flex; align-items: center; gap: .75rem; }
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
        min-height: 590px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
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
      .auth-benefits {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: .65rem;
        margin-top: 2rem;
      }
      .auth-benefit {
        padding: .9rem;
        border-radius: 16px;
        background: rgba(255,255,255,.12);
        border: 1px solid rgba(255,255,255,.16);
        font-size: .8rem;
        font-weight: 700;
      }
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
      .product-brand { color: var(--sp-muted); font-size: .72rem; font-weight: 800; letter-spacing:.06em; margin-top:.65rem; }
      .product-name { font-size: 1.06rem; font-weight: 800; margin: .3rem 0; letter-spacing:-.025em; }
      .product-description { color: var(--sp-muted); font-size: .84rem; min-height: 3.6rem; line-height:1.55; }
      .product-meta { display:flex; justify-content:space-between; margin-top:.8rem; }
      .reason {
        background: #f0fdf4; border: 1px solid #bbf7d0; color:#166534;
        border-radius: 12px; padding: .65rem; min-height: 4.2rem; font-size: .84rem;
        margin-top: .7rem;
      }
      [data-testid="stMetric"] {
        background:white; border:1px solid var(--sp-line); border-radius:16px; padding:14px;
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

      @media (max-width: 900px) {
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
          padding: .7rem .8rem 7.4rem;
        }
        .store-header {
          position: sticky;
          top: .45rem;
          z-index: 90;
          padding: .58rem .65rem;
          border-radius: 15px;
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
        .auth-hero { min-height: 430px; padding: 2rem 1.35rem; border-radius: 22px; }
        .auth-benefits { grid-template-columns: 1fr; }
        .auth-panel { padding: .5rem .1rem 1rem; }
        .section-heading { margin-top: 1.2rem; }
        div[data-testid="stHorizontalBlock"]:has(.product-card) {
          flex-wrap: wrap;
          gap: .35rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.product-card) > div[data-testid="stColumn"] {
          flex: 1 1 100%;
          width: 100%;
          min-width: 100%;
        }
        .product-card { min-height: 0; }
        .product-description { min-height: 0; }
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
def get_database_future(database_url: str) -> Future:
    return start_daemon_future(
        build_database,
        database_url,
        thread_name="stylepick-database",
    )


@st.cache_resource(show_spinner=False)
def get_database_sync(database_url: str) -> StoreDatabase:
    return build_database(database_url)


class LazyDatabase:
    """Delay waiting for the remote DB until an authentication action needs it."""

    def __init__(self, future: Future) -> None:
        self.future = future

    def __getattr__(self, name: str):
        return getattr(self.future.result(), name)


if os.environ.get("STYLEPICK_TEST_SYNC_STARTUP") == "1":
    database_future = Future()
    database_future.set_result(get_database_sync(DATABASE_TARGET))
else:
    database_future = get_database_future(DATABASE_TARGET)
database = LazyDatabase(database_future)
RECOMMENDER_BACKEND = os.environ.get("RECOMMENDER_BACKEND", "tfidf").lower()


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


def initialize_auth() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"session_{uuid4().hex[:12]}"
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if os.environ.get("STYLEPICK_TEST_AUTOLOGIN") == "1" and not st.session_state.user_id:
        login_user(database.ensure_demo_user())


def login_user(user: dict) -> None:
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


def submit_login() -> None:
    st.session_state.pop("login_error", None)
    try:
        login_user(
            database.authenticate(
                st.session_state.get("login_email", ""),
                st.session_state.get("login_password", ""),
            )
        )
        st.session_state.auth_notice = (
            "DB에 저장된 계정 정보를 확인하고 로그인했습니다."
        )
    except ValueError as error:
        st.session_state.login_error = str(error)


def start_demo() -> None:
    login_user(database.ensure_demo_user())


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


def logout_user() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


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
        saved_nickname = (
            st.session_state.get("profile_nickname", "").strip() or "게스트"
        )
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
              <div class="auth-benefits">
                <div class="auth-benefit">✨ 자연어 AI 추천</div>
                <div class="auth-benefit">🔒 비밀번호 해시 저장</div>
                <div class="auth-benefit">📱 모바일 반응형</div>
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


def complete_order() -> None:
    st.session_state.pop("checkout_error", None)
    try:
        wait_for_pending_cart_writes()
        order = database.create_order(
            int(st.session_state.user_id),
            st.session_state.session_id,
        )
        st.session_state.last_order = order
        st.session_state.order_history = [
            order,
            *st.session_state.get("order_history", []),
        ][:5]
        st.session_state.cart = {}
    except ValueError as error:
        st.session_state.checkout_error = str(error)


def reset_last_order() -> None:
    st.session_state.last_order = None


def open_product_detail(product_id: str, reason: str | None = None) -> None:
    st.session_state.selected_product_id = product_id
    st.session_state.selected_product_reason = reason
    database.log_behavior_async(
        int(st.session_state.user_id),
        st.session_state.session_id,
        product_id,
        "VIEW",
    )


def close_product_detail() -> None:
    st.session_state.selected_product_id = None
    st.session_state.selected_product_reason = None
    st.session_state.pop("detail_order", None)


def buy_product_now(product_id: str) -> None:
    st.session_state.pop("detail_order_error", None)
    try:
        wait_for_pending_cart_writes()
        quantity = int(
            st.session_state.get(f"detail_quantity_{product_id}", 1)
        )
        order = database.create_product_order(
            int(st.session_state.user_id),
            st.session_state.session_id,
            product_id,
            quantity,
        )
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
    st.button(
        "← 쇼핑으로 돌아가기",
        key="detail_back",
        on_click=close_product_detail,
    )
    visual_col, info_col = st.columns([1, 1.15], gap="large")
    with visual_col:
        st.markdown(
            f"""
            <div class="product-card" style="min-height:360px;display:grid;place-items:center">
              <div style="font-size:9rem">{product['emoji']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with info_col:
        st.caption(
            f"{product['brand']} · {product['category']} · ⭐ {product['rating']}"
        )
        st.title(product["name"])
        st.write(product["description"])
        if reason := st.session_state.get("selected_product_reason"):
            st.success(f"✨ {reason}")
        st.markdown(f"**상품 태그** · {product['tags']}")
        price_col, stock_col = st.columns(2)
        price_col.metric("판매가", f"{int(product['price']):,}원")
        stock_col.metric("현재 재고", f"{int(product['stock'])}개")
        st.number_input(
            "구매 수량",
            min_value=1,
            max_value=min(10, int(product["stock"])),
            value=1,
            key=f"detail_quantity_{product_id}",
        )

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


# Load the local catalog and E5 in a background thread. The main thread only
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
if not st.session_state.user_id:
    render_auth()
    st.stop()

try:
    database = database_future.result()
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
storefront_snapshot = st.session_state.pop("storefront_snapshot_ready", None)
if storefront_snapshot is None:
    storefront_snapshot = get_storefront_snapshot(
        DATABASE_TARGET,
        int(st.session_state.user_id),
        database,
    )
initialize_state(storefront_snapshot)
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
if selected_product_id := st.session_state.get("selected_product_id"):
    render_product_detail_page(str(selected_product_id))
    st.stop()

with st.sidebar:
    st.caption(f"로그인: {current_user['email']}")
    st.header("👤 나의 취향 설정")
    with st.form("profile_form"):
        st.text_input(
            "닉네임",
            key="profile_nickname",
        )
        st.multiselect(
            "관심 카테고리",
            CATEGORIES,
            max_selections=3,
            key="profile_interests",
        )
        st.slider(
            "관심 가격대",
            min_value=0,
            max_value=MAX_PRICE,
            step=5_000,
            format="%d원",
            key="profile_budget",
        )
        st.form_submit_button(
            "취향 저장",
            type="primary",
            width="stretch",
            on_click=save_profile_settings,
        )
    if st.session_state.pop("profile_saved_notice", False):
        st.toast("취향이 추천에 반영됐어요.")
    if profile_error := st.session_state.get("profile_error"):
        st.error(profile_error)
    st.divider()
    st.metric("찜한 상품", len(st.session_state.favorites))
    st.metric("장바구니 수량", sum(st.session_state.cart.values()))
    st.caption(
        f"개인화 행동 {sum(behavior_summary.values()):,}건이 추천에 반영됩니다."
    )
    st.button("로그아웃", width="stretch", on_click=logout_user)
    with st.expander("회원탈퇴"):
        st.warning("탈퇴하면 계정, 취향, 찜, 장바구니, 행동 및 주문 데이터가 즉시 삭제됩니다.")
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
            if delete_error := st.session_state.get("delete_account_error"):
                st.error(delete_error)

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

st.markdown(
    f"""
    <div class="store-shell-marker"></div>
    <header class="store-header">
      <div class="brand-lockup">
        <div class="brand-mark">SP</div>
        <div>
          <div class="brand-name">StylePick AI</div>
          <div class="brand-caption">나를 이해하는 설명 가능한 쇼핑</div>
        </div>
      </div>
      <div class="header-status">
        <span class="status-chip">👤 {escape(st.session_state.nickname)}님</span>
        <span class="status-chip">♥ {len(st.session_state.favorites)}</span>
        <span class="status-chip">🛒 {sum(st.session_state.cart.values())}</span>
      </div>
    </header>
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

shop_tab, recommend_tab, favorite_tab, cart_tab = st.tabs(
    ["🛍️ 상품 탐색", "✨ AI 추천", "♥ 찜 목록", "🛒 장바구니·주문"]
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
    else:
        st.success(
            "관심사와 최근 클릭·찜·장바구니·구매 행동을 반영한 회원별 추천입니다."
        )
    with st.expander("추천 점수는 어떻게 계산되나요?"):
        st.code(
            "개인화 점수 = 콘텐츠 유사도×0.30 + 카테고리×0.20 "
            "+ 최근 행동 유사도×0.20 + 예산×0.10 + 최근 트렌드×0.10 "
            "+ 평점×0.10 - 부정 행동 패널티"
        )
        st.write(
            "TF-IDF가 상품명·카테고리·설명에서 중요한 단어를 학습하고, "
            "사용자 취향 및 최근 행동 벡터와 상품 벡터의 코사인 유사도를 계산합니다. "
            "행동은 클릭 1, 찜 4, 장바구니 5, 구매 8점이며 최근 행동을 더 크게 반영합니다. "
            "찜·장바구니에서 제거한 상품은 추천 점수가 낮아집니다."
        )
        st.caption(
            f"텍스트 모델 {RECOMMENDER_BACKEND.upper()} · "
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
        if checkout_error := st.session_state.get("checkout_error"):
            st.error(checkout_error)

    order_history = st.session_state.order_history
    if order_history:
        with st.expander("최근 모의 주문 내역"):
            for order in order_history:
                names = ", ".join(item["name"] for item in order["items"])
                st.write(
                    f"**{order['order_id']}** · {order['total']:,}원 · "
                    f"{order['ordered_at']}"
                )
                st.caption(names)

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
