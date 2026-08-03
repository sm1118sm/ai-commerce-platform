"""Read-only daily operations reporting for StylePick AI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping


ACTION_LABELS = {
    "VIEW": "상품 조회",
    "SEARCH": "검색",
    "WISHLIST_ADD": "찜 추가",
    "WISHLIST_REMOVE": "찜 해제",
    "CART_ADD": "장바구니 추가",
    "CART_REMOVE": "장바구니 제거",
    "PURCHASE": "구매 상품",
    "PURCHASE_CANCEL": "구매 취소 상품",
}


@dataclass(frozen=True)
class RankedItem:
    name: str
    count: int
    detail: str = ""


@dataclass(frozen=True)
class DailySnapshot:
    report_date: str
    source: str = "운영 DB (읽기 전용)"
    total_users: int = 0
    new_users: int = 0
    active_users: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    previous_actions: dict[str, int] = field(default_factory=dict)
    paid_orders: int = 0
    canceled_orders: int = 0
    paid_revenue: int = 0
    paid_quantity: int = 0
    top_products: tuple[RankedItem, ...] = ()
    search_keywords: tuple[RankedItem, ...] = ()
    low_stock_products: tuple[RankedItem, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DailySnapshot":
        def ranked(key: str) -> tuple[RankedItem, ...]:
            return tuple(RankedItem(**item) for item in payload.get(key, []))

        return cls(
            report_date=str(payload["report_date"]),
            source=str(payload.get("source", "테스트 입력")),
            total_users=int(payload.get("total_users", 0)),
            new_users=int(payload.get("new_users", 0)),
            active_users=int(payload.get("active_users", 0)),
            actions={
                str(key): int(value)
                for key, value in payload.get("actions", {}).items()
            },
            previous_actions={
                str(key): int(value)
                for key, value in payload.get("previous_actions", {}).items()
            },
            paid_orders=int(payload.get("paid_orders", 0)),
            canceled_orders=int(payload.get("canceled_orders", 0)),
            paid_revenue=int(payload.get("paid_revenue", 0)),
            paid_quantity=int(payload.get("paid_quantity", 0)),
            top_products=ranked("top_products"),
            search_keywords=ranked("search_keywords"),
            low_stock_products=ranked("low_stock_products"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _date_bounds(report_date: date) -> tuple[str, str]:
    return report_date.isoformat(), (report_date + timedelta(days=1)).isoformat()


def _action_counts(connection, start: str, end: str) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT action_type, COUNT(*) AS count
        FROM behavior_logs
        WHERE created_at >= ? AND created_at < ?
        GROUP BY action_type
        """,
        (start, end),
    ).fetchall()
    return {str(row["action_type"]): int(row["count"]) for row in rows}


def collect_daily_snapshot(
    database,
    report_date: date,
    *,
    low_stock_threshold: int = 5,
) -> DailySnapshot:
    """Collect one day's metrics without changing application data."""
    start, end = _date_bounds(report_date)
    previous_start, _ = _date_bounds(report_date - timedelta(days=1))
    with database.connect() as connection:
        actions = _action_counts(connection, start, end)
        previous_actions = _action_counts(connection, previous_start, start)

        user_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN created_at >= ? AND created_at < ? THEN 1 ELSE 0 END)
                    AS new_users
            FROM users
            """,
            (start, end),
        ).fetchone()
        active_row = connection.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS active_users
            FROM behavior_logs
            WHERE created_at >= ? AND created_at < ?
            """,
            (start, end),
        ).fetchone()
        order_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN status <> 'CANCELED_DEMO' THEN 1 ELSE 0 END)
                    AS paid_orders,
                SUM(CASE WHEN status = 'CANCELED_DEMO' THEN 1 ELSE 0 END)
                    AS canceled_orders,
                SUM(CASE WHEN status <> 'CANCELED_DEMO' THEN total ELSE 0 END)
                    AS paid_revenue,
                SUM(CASE WHEN status <> 'CANCELED_DEMO' THEN quantity ELSE 0 END)
                    AS paid_quantity
            FROM user_orders
            WHERE ordered_at >= ? AND ordered_at < ?
            """,
            (start, end),
        ).fetchone()
        top_product_rows = connection.execute(
            """
            SELECT oi.product_name AS name, SUM(oi.quantity) AS count,
                   oi.product_id AS detail
            FROM order_items oi
            JOIN user_orders o ON o.order_id = oi.order_id
            WHERE o.ordered_at >= ? AND o.ordered_at < ?
              AND o.status <> 'CANCELED_DEMO'
            GROUP BY oi.product_id, oi.product_name
            ORDER BY count DESC, oi.product_id
            LIMIT 5
            """,
            (start, end),
        ).fetchall()
        search_rows = connection.execute(
            """
            SELECT search_keyword AS name, COUNT(*) AS count
            FROM behavior_logs
            WHERE created_at >= ? AND created_at < ?
              AND action_type = 'SEARCH'
              AND search_keyword IS NOT NULL AND search_keyword <> ''
            GROUP BY search_keyword
            ORDER BY count DESC, search_keyword
            LIMIT 5
            """,
            (start, end),
        ).fetchall()
        low_stock_rows = connection.execute(
            """
            SELECT name, stock AS count, product_id AS detail
            FROM products
            WHERE stock <= ?
            ORDER BY stock, product_id
            LIMIT 10
            """,
            (int(low_stock_threshold),),
        ).fetchall()

    def number(row, key: str) -> int:
        return int((row or {}).get(key) or 0)

    def items(rows) -> tuple[RankedItem, ...]:
        return tuple(
            RankedItem(
                name=str(row["name"]),
                count=int(row["count"]),
                detail=str(row.get("detail") or ""),
            )
            for row in rows
        )

    return DailySnapshot(
        report_date=start,
        total_users=number(user_row, "total_users"),
        new_users=number(user_row, "new_users"),
        active_users=number(active_row, "active_users"),
        actions=actions,
        previous_actions=previous_actions,
        paid_orders=number(order_row, "paid_orders"),
        canceled_orders=number(order_row, "canceled_orders"),
        paid_revenue=number(order_row, "paid_revenue"),
        paid_quantity=number(order_row, "paid_quantity"),
        top_products=items(top_product_rows),
        search_keywords=items(search_rows),
        low_stock_products=items(low_stock_rows),
    )


def _change_text(current: int, previous: int) -> str:
    if previous == 0:
        return "전일 0건" if current == 0 else "전일 비교 기준 없음"
    change = ((current - previous) / previous) * 100
    return f"전일 대비 {change:+.1f}%"


def _rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "계산 불가"
    return f"{numerator / denominator * 100:.1f}%"


def build_attention_items(snapshot: DailySnapshot) -> list[str]:
    """Return deterministic, evidence-based checks for the operator."""
    items: list[str] = []
    if snapshot.low_stock_products:
        lowest = snapshot.low_stock_products[0]
        items.append(
            f"저재고 상품이 {len(snapshot.low_stock_products)}개입니다. "
            f"가장 적은 상품은 {lowest.name}({lowest.count}개)입니다."
        )
    if snapshot.canceled_orders:
        items.append(f"취소 주문 {snapshot.canceled_orders}건을 확인하세요.")
    searches = snapshot.actions.get("SEARCH", 0)
    if searches and snapshot.paid_orders == 0:
        items.append(
            f"검색 {searches}건이 있었지만 완료 주문은 없습니다. "
            "검색 결과와 상품 구성을 확인하세요."
        )
    cart_adds = snapshot.actions.get("CART_ADD", 0)
    views = snapshot.actions.get("VIEW", 0)
    if views >= 10 and cart_adds / views < 0.1:
        items.append("상품 조회 대비 장바구니 추가 비율이 10% 미만입니다.")
    if not items:
        items.append("자동 기준에서 즉시 확인할 주의 항목이 없습니다.")
    return items[:3]


def render_daily_report(snapshot: DailySnapshot) -> str:
    actions = snapshot.actions
    previous = snapshot.previous_actions
    action_lines = [
        f"| {label} | {actions.get(action, 0):,} | "
        f"{_change_text(actions.get(action, 0), previous.get(action, 0))} |"
        for action, label in ACTION_LABELS.items()
    ]

    def ranked_lines(items: tuple[RankedItem, ...], unit: str) -> list[str]:
        if not items:
            return ["- 기록 없음"]
        return [
            f"- {item.name}: {item.count:,}{unit}"
            + (f" (`{item.detail}`)" if item.detail else "")
            for item in items
        ]

    attention = [
        f"{index}. {item}"
        for index, item in enumerate(build_attention_items(snapshot), start=1)
    ]
    view_count = actions.get("VIEW", 0)
    cart_count = actions.get("CART_ADD", 0)
    purchase_count = actions.get("PURCHASE", 0)
    return "\n".join(
        [
            f"# {snapshot.report_date} StylePick AI 일일 운영 보고서",
            "",
            f"> 데이터 원천: {snapshot.source}",
            "> 이 보고서는 읽기 전용으로 생성되며 주문·상품·재고를 변경하지 않습니다.",
            "",
            "## 핵심 지표",
            "",
            f"- 전체 등록 회원: {snapshot.total_users:,}명",
            f"- 신규 회원: {snapshot.new_users:,}명",
            f"- 활동 회원: {snapshot.active_users:,}명",
            f"- 완료 주문: {snapshot.paid_orders:,}건 / {snapshot.paid_quantity:,}개",
            f"- 모의 매출: {snapshot.paid_revenue:,}원",
            f"- 취소 주문: {snapshot.canceled_orders:,}건",
            "",
            "## 행동 지표",
            "",
            "| 행동 | 당일 | 변화 |",
            "| --- | ---: | --- |",
            *action_lines,
            "",
            "## 간이 전환 흐름",
            "",
            f"- 조회 → 장바구니 추가: {_rate(cart_count, view_count)}",
            f"- 장바구니 추가 → 구매 상품: {_rate(purchase_count, cart_count)}",
            "- 동일 사용자의 연속 퍼널이 아닌 일별 행동 건수 비율입니다.",
            "",
            "## 판매 상위 상품",
            "",
            *ranked_lines(snapshot.top_products, "개"),
            "",
            "## 검색 키워드",
            "",
            *ranked_lines(snapshot.search_keywords, "회"),
            "",
            "## 저재고 상품",
            "",
            *ranked_lines(snapshot.low_stock_products, "개"),
            "",
            "## 오늘 확인할 항목",
            "",
            *attention,
            "",
            "## 해석 제한",
            "",
            "- 추천 노출 여부가 저장되지 않아 추천 클릭률은 계산하지 않았습니다.",
            "- 검색과 주문의 직접 연결 키가 없어 검색별 구매 전환은 계산하지 않았습니다.",
            "- 모의 주문 데이터이므로 매출은 실제 결제액이 아닙니다.",
            "",
        ]
    )
