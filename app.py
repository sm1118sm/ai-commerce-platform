"""StylePick AI: a three-day-hackathon personalized commerce MVP."""

from __future__ import annotations

from html import escape
import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from src.catalog import load_products
from src.database import StoreDatabase
from src.recommender import fit_recommender, recommend


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
      .stApp {
        background: #f7f8fc;
        color: #172033;
        color-scheme: light;
      }
      [data-testid="stWidgetLabel"] p,
      [data-testid="stCaptionContainer"] p,
      [data-testid="stMarkdownContainer"] > p,
      button[data-baseweb="tab"] p {
        color: #172033 !important;
      }
      div[data-baseweb="input"] input,
      div[data-baseweb="base-input"] input {
        background: #ffffff !important;
        color: #172033 !important;
        -webkit-text-fill-color: #172033 !important;
      }
      .block-container { max-width: 1240px; padding-top: 2rem; padding-bottom: 5rem; }
      .hero {
        padding: 2.2rem; border-radius: 24px; color: white; margin-bottom: 1rem;
        background: linear-gradient(120deg, #4f46e5, #7c3aed 50%, #ec4899);
        box-shadow: 0 18px 40px rgba(79,70,229,.18);
      }
      .hero h1 { margin: 0 0 .4rem 0; font-size: 2.35rem; }
      .hero p { margin: 0; opacity: .9; font-size: 1.05rem; }
      .product-card {
        min-height: 250px; background: white; border: 1px solid #e8eaf2;
        border-radius: 18px; padding: 1.15rem; margin-top: .5rem;
        box-shadow: 0 6px 22px rgba(15,23,42,.055);
      }
      .product-emoji { font-size: 3.3rem; text-align: center; padding: .4rem; }
      .product-category { color: #6d5dfc; font-size: .82rem; font-weight: 700; }
      .product-name { font-size: 1.08rem; font-weight: 750; margin: .35rem 0; }
      .product-description { color: #64748b; font-size: .88rem; min-height: 3.8rem; }
      .product-meta { display:flex; justify-content:space-between; margin-top:.8rem; }
      .reason {
        background: #f0fdf4; border: 1px solid #bbf7d0; color:#166534;
        border-radius: 12px; padding: .65rem; min-height: 4.2rem; font-size: .84rem;
        margin-top: .7rem;
      }
      [data-testid="stMetric"] {
        background:white; border:1px solid #e8eaf2; border-radius:14px; padding:14px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def get_products() -> pd.DataFrame:
    return load_products(PRODUCT_PATH)


database = StoreDatabase(DATABASE_TARGET)
database.seed_products(get_products())
products = database.load_products()
model = fit_recommender(products)
CATEGORIES = sorted(products["category"].unique().tolist())
MAX_PRICE = int(products["price"].max())


def initialize_auth() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"session_{uuid4().hex[:12]}"
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if os.environ.get("STYLEPICK_TEST_AUTOLOGIN") == "1" and not st.session_state.user_id:
        demo = database.ensure_demo_user()
        st.session_state.user_id = int(demo["id"])


def login_user(user: dict) -> None:
    st.session_state.user_id = int(user["id"])
    st.session_state.loaded_user_id = None
    st.session_state.last_order = None


def render_auth() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>StylePick AI</h1>
          <p>회원별 행동을 학습하는 설명 가능한 개인화 쇼핑</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("취향과 행동 데이터를 안전하게 분리 저장하려면 로그인해 주세요.")
    if st.session_state.pop("account_deleted_notice", False):
        st.success("회원 정보와 연결 데이터가 모두 삭제되었습니다.")
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("이메일", placeholder="name@example.com")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button(
                "로그인",
                type="primary",
                width="stretch",
            )
            if submitted:
                try:
                    login_user(database.authenticate(email, password))
                    st.session_state.auth_notice = (
                        "DB에 저장된 계정 정보를 확인하고 로그인했습니다."
                    )
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        if st.button("데모 계정으로 바로 시작", width="stretch"):
            login_user(database.ensure_demo_user())
            st.rerun()
        st.caption("데모 계정은 로컬 시연용이며 실제 결제는 발생하지 않습니다.")
    with signup_tab:
        with st.form("signup_form"):
            signup_email = st.text_input(
                "이메일",
                key="signup_email",
                max_chars=120,
            )
            signup_nickname = st.text_input(
                "닉네임",
                key="signup_nickname",
                max_chars=30,
            )
            signup_phone = st.text_input(
                "전화번호",
                key="signup_phone",
                placeholder="010-1234-5678",
                max_chars=20,
            )
            signup_password = st.text_input(
                "비밀번호",
                type="password",
                key="signup_password",
                help="8자 이상 입력하세요.",
            )
            signup_confirm = st.text_input(
                "비밀번호 확인",
                type="password",
                key="signup_confirm",
            )
            signup_submitted = st.form_submit_button(
                "회원가입",
                type="primary",
                width="stretch",
            )
            if signup_submitted:
                if signup_password != signup_confirm:
                    st.error("비밀번호 확인이 일치하지 않습니다.")
                else:
                    try:
                        created_user = database.register_user(
                            signup_email,
                            signup_password,
                            signup_nickname,
                            signup_phone,
                        )
                        user = database.authenticate(
                            signup_email,
                            signup_password,
                        )
                        if int(user["id"]) != int(created_user["id"]):
                            raise ValueError(
                                "회원가입 정보 저장을 확인하지 못했습니다."
                            )
                        login_user(user)
                        st.session_state.auth_notice = (
                            "회원가입 정보가 DB에 저장되고 로그인되었습니다."
                        )
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))


def initialize_state() -> None:
    user_id = int(st.session_state.user_id)
    if st.session_state.get("loaded_user_id") == user_id:
        return
    profile = database.load_profile(user_id)
    st.session_state.nickname = profile["nickname"]
    st.session_state.interests = profile["interests"]
    st.session_state.budget = profile["budget"]
    st.session_state.favorites = database.load_favorites(user_id)
    st.session_state.cart = database.load_cart(user_id)
    st.session_state.last_order = None
    st.session_state.loaded_user_id = user_id


def toggle_favorite(product_id: str) -> None:
    added = database.toggle_favorite(
        int(st.session_state.user_id),
        product_id,
        st.session_state.session_id,
    )
    st.session_state.favorites = database.load_favorites(
        int(st.session_state.user_id)
    )
    if added:
        st.toast("관심 상품으로 저장했어요. 추천에 반영됩니다.")
    else:
        st.toast("찜 목록에서 제거했어요.")


def add_to_cart(product_id: str) -> None:
    try:
        database.add_to_cart(
            int(st.session_state.user_id),
            product_id,
            st.session_state.session_id,
        )
        st.session_state.cart = database.load_cart(int(st.session_state.user_id))
        st.toast("장바구니에 담았습니다.")
    except ValueError as error:
        st.error(str(error))


@st.dialog("상품 상세")
def product_detail(product_id: str) -> None:
    product = products.loc[products["id"] == product_id].iloc[0]
    st.markdown(
        f"<div style='font-size:5rem;text-align:center'>{product['emoji']}</div>",
        unsafe_allow_html=True,
    )
    st.subheader(product["name"])
    st.caption(f"{product['category']} · ⭐ {product['rating']}")
    st.write(product["description"])
    st.metric("판매가", f"{int(product['price']):,}원")
    st.caption(f"현재 재고: {int(product['stock'])}개")
    left, right = st.columns(2)
    favorite_label = (
        "찜 해제" if product_id in st.session_state.favorites else "♡ 찜하기"
    )
    if left.button(favorite_label, key=f"dialog_fav_{product_id}", width="stretch"):
        toggle_favorite(product_id)
        st.rerun()
    if right.button(
        "품절" if int(product["stock"]) <= 0 else "장바구니 담기",
        key=f"dialog_cart_{product_id}",
        type="primary",
        width="stretch",
        disabled=int(product["stock"]) <= 0,
    ):
        add_to_cart(product_id)
        st.rerun()


def product_card(product: pd.Series, key_prefix: str, reason: str | None = None) -> None:
    description = escape(str(product["description"]))
    reason_html = (
        f"<div class='reason'>✨ {escape(reason)}</div>" if reason else ""
    )
    st.markdown(
        f"""
        <div class="product-card">
          <div class="product-emoji">{product['emoji']}</div>
          <div class="product-category">{escape(str(product['category']))}</div>
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
    if detail_col.button(
        "상세",
        key=f"{key_prefix}_detail_{product['id']}",
        width="stretch",
    ):
        database.log_behavior(
            int(st.session_state.user_id),
            st.session_state.session_id,
            str(product["id"]),
            "VIEW",
        )
        product_detail(str(product["id"]))
    favorite_icon = "♥" if product["id"] in st.session_state.favorites else "♡"
    if favorite_col.button(
        favorite_icon,
        key=f"{key_prefix}_favorite_{product['id']}",
        width="stretch",
    ):
        toggle_favorite(str(product["id"]))
        st.rerun()
    if cart_col.button(
        "품절" if int(product["stock"]) <= 0 else "담기",
        key=f"{key_prefix}_cart_{product['id']}",
        type="primary",
        width="stretch",
        disabled=int(product["stock"]) <= 0,
    ):
        add_to_cart(str(product["id"]))
        st.rerun()


def product_grid(
    frame: pd.DataFrame,
    key_prefix: str,
    show_reasons: bool = False,
) -> None:
    if frame.empty:
        st.info("조건에 맞는 상품이 없습니다.")
        return
    rows = frame.reset_index(drop=True)
    for start in range(0, len(rows), 3):
        columns = st.columns(3)
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


initialize_auth()
if not st.session_state.user_id:
    render_auth()
    st.stop()
initialize_state()
current_user = database.get_user(int(st.session_state.user_id))
if auth_notice := st.session_state.pop("auth_notice", None):
    st.toast(auth_notice, icon="✅")

with st.sidebar:
    st.caption(f"로그인: {current_user['email']}")
    st.header("👤 나의 취향 설정")
    with st.form("profile_form"):
        nickname = st.text_input("닉네임", value=st.session_state.nickname)
        interests = st.multiselect(
            "관심 카테고리",
            CATEGORIES,
            default=st.session_state.interests,
            max_selections=3,
        )
        budget = st.slider(
            "관심 가격대",
            min_value=0,
            max_value=MAX_PRICE,
            value=st.session_state.budget,
            step=5_000,
            format="%d원",
        )
        if st.form_submit_button("취향 저장", type="primary", width="stretch"):
            try:
                saved_nickname = nickname.strip() or "게스트"
                database.save_profile(
                    int(st.session_state.user_id),
                    saved_nickname,
                    list(interests),
                    tuple(budget),
                )
                st.session_state.nickname = saved_nickname
                st.session_state.interests = interests
                st.session_state.budget = budget
                st.toast("취향이 추천에 반영됐어요.")
            except ValueError as error:
                st.error(str(error))
    st.divider()
    st.metric("찜한 상품", len(st.session_state.favorites))
    st.metric("장바구니 수량", sum(st.session_state.cart.values()))
    behavior_summary = database.behavior_summary(int(st.session_state.user_id))
    st.caption(
        f"개인화 행동 {sum(behavior_summary.values()):,}건이 추천에 반영됩니다."
    )
    if st.button("로그아웃", width="stretch"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    with st.expander("회원탈퇴"):
        st.warning("탈퇴하면 계정, 취향, 찜, 장바구니, 행동 및 주문 데이터가 즉시 삭제됩니다.")
        with st.form("delete_account_form"):
            delete_password = st.text_input(
                "현재 비밀번호",
                type="password",
                key="delete_account_password",
            )
            delete_confirmed = st.checkbox(
                "삭제된 데이터는 복구할 수 없음을 확인했습니다."
            )
            if st.form_submit_button(
                "계정 영구 삭제",
                disabled=not delete_confirmed,
                width="stretch",
            ):
                try:
                    database.delete_user(
                        int(st.session_state.user_id),
                        delete_password,
                    )
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.session_state.account_deleted_notice = True
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

st.markdown(
    f"""
    <div class="hero">
      <h1>StylePick AI</h1>
      <p>{escape(st.session_state.nickname)}님을 위한 설명 가능한 AI 쇼핑 큐레이션</p>
    </div>
    """,
    unsafe_allow_html=True,
)

shop_tab, recommend_tab, favorite_tab, cart_tab = st.tabs(
    ["🛍️ 상품 탐색", "✨ AI 추천", "♥ 찜 목록", "🛒 장바구니·주문"]
)

with shop_tab:
    st.subheader("상품 탐색")
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
    product_grid(filtered, "shop")

with recommend_tab:
    st.subheader(f"{st.session_state.nickname}님을 위한 AI 추천")
    budget_min, budget_max = st.session_state.budget
    behavior_weights = database.user_behavior_weights(
        int(st.session_state.user_id)
    )
    trend_scores = database.trend_scores(days=7)
    purchased_ids = database.purchased_product_ids(
        int(st.session_state.user_id)
    )
    recommendations = recommend(
        products=products,
        model=model,
        interests=list(st.session_state.interests),
        favorite_ids=set(st.session_state.favorites),
        budget_min=budget_min,
        budget_max=budget_max,
        top_n=12,
        behavior_product_weights=behavior_weights,
        trend_product_scores=trend_scores,
        purchased_ids=purchased_ids,
    )
    if (
        not st.session_state.interests
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
            "개인화 점수 = 콘텐츠 유사도×0.35 + 카테고리×0.20 "
            "+ 최근 행동 유사도×0.20 + 예산×0.10 + 최근 트렌드×0.15"
        )
        st.write(
            "TF-IDF가 상품명·카테고리·설명에서 중요한 단어를 학습하고, "
            "사용자 취향 및 최근 행동 벡터와 상품 벡터의 코사인 유사도를 계산합니다. "
            "행동은 클릭 1, 찜 4, 장바구니 5, 구매 8점이며 최근 행동을 더 크게 반영합니다."
        )
        st.caption(
            f"현재 반영된 행동 상품 {len(behavior_weights)}개 · "
            f"최근 7일 트렌드 상품 {len(trend_scores)}개 · "
            f"구매 완료 제외 상품 {len(purchased_ids)}개"
        )
    product_grid(recommendations, "recommend", show_reasons=True)

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
        if st.button("새 쇼핑 계속하기"):
            st.session_state.last_order = None
            st.rerun()

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
                if delete_col.button("삭제", key=f"delete_soldout_{product_id}"):
                    database.remove_cart_item(
                        int(st.session_state.user_id),
                        product_id,
                        st.session_state.session_id,
                    )
                    st.session_state.cart = database.load_cart(
                        int(st.session_state.user_id)
                    )
                    st.rerun()
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
                database.set_cart_quantity(
                    int(st.session_state.user_id),
                    product_id,
                    int(quantity),
                )
                st.session_state.cart[product_id] = int(quantity)
            line_total = int(item["price"]) * int(quantity)
            total += line_total
            price_col.write(f"**{line_total:,}원**")
            if delete_col.button("삭제", key=f"delete_{product_id}"):
                database.remove_cart_item(
                    int(st.session_state.user_id),
                    product_id,
                    st.session_state.session_id,
                )
                del st.session_state.cart[product_id]
                st.rerun()
            st.divider()

        summary_col, checkout_col = st.columns([2, 1])
        summary_col.metric("모의 결제 합계", f"{total:,}원")
        summary_col.caption("최종 금액과 재고는 주문 시 서버에서 다시 검증합니다.")
        if checkout_col.button(
            "모의 주문 완료",
            type="primary",
            width="stretch",
        ):
            try:
                st.session_state.last_order = database.create_order(
                    int(st.session_state.user_id),
                    st.session_state.session_id,
                )
                st.session_state.cart = {}
                st.balloons()
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    order_history = database.list_orders(
        int(st.session_state.user_id),
        limit=5,
    )
    if order_history:
        with st.expander("최근 모의 주문 내역"):
            for order in order_history:
                names = ", ".join(item["name"] for item in order["items"])
                st.write(
                    f"**{order['order_id']}** · {order['total']:,}원 · "
                    f"{order['ordered_at']}"
                )
                st.caption(names)
