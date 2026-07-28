"""Measure every storefront button action five times with Streamlit AppTest.

The script intentionally requires a database whose name ends in ``_test``.
It clears that database before the run, creates disposable members, and never
touches the production database.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from time import perf_counter

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database import StoreDatabase
from tests.test_database import reset_test_database


REPEAT_COUNT = 5
RESPONSE_BUDGET_SECONDS = 2.0
TEST_DATABASE_URL = os.environ.get("STYLEPICK_TEST_DATABASE_URL", "")
TEST_PASSWORD = "Latency-test!"
PRODUCT_ID = "P028"
DETAIL_PRODUCT_ID = "P020"


class ButtonLatencyRun:
    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = defaultdict(list)

    @staticmethod
    def button(app: AppTest, *, label: str | None = None, key: str | None = None):
        return next(
            button
            for button in app.button
            if (label is None or button.label == label)
            and (key is None or button.key == key)
        )

    @staticmethod
    def text_input(app: AppTest, key: str):
        return next(field for field in app.text_input if field.key == key)

    def click(
        self,
        app: AppTest,
        action: str,
        *,
        label: str | None = None,
        key: str | None = None,
        record: bool = True,
    ) -> float:
        started_at = perf_counter()
        self.button(app, label=label, key=key).click().run()
        elapsed_seconds = perf_counter() - started_at
        if app.exception:
            raise AssertionError(
                f"{action} 실행 중 Streamlit 예외가 발생했습니다: "
                f"{[error.value for error in app.exception]}"
            )
        if record:
            self.samples[action].append(elapsed_seconds)
            print(
                f"{action} #{len(self.samples[action])}: "
                f"{elapsed_seconds:.3f}s"
            )
        return elapsed_seconds

    @staticmethod
    def new_auth_app() -> AppTest:
        os.environ.pop("STYLEPICK_TEST_AUTOLOGIN", None)
        return AppTest.from_file(
            str(ROOT / "app.py"),
            default_timeout=120,
        ).run()

    def measure_login_and_logout(self, database: StoreDatabase) -> None:
        email = "latency-login@example.com"
        database.register_user(
            email,
            TEST_PASSWORD,
            "로그인지연측정",
            "010-1111-2222",
        )
        app = self.new_auth_app()
        for _ in range(REPEAT_COUNT):
            self.text_input(app, "login_email").input(email)
            self.text_input(app, "login_password").input(TEST_PASSWORD)
            self.click(app, "로그인", label="로그인")
            if app.session_state["user_id"] is None:
                raise AssertionError("로그인 버튼이 사용자 세션을 만들지 못했습니다.")
            self.click(app, "로그아웃", label="로그아웃")
            if app.session_state["user_id"] is not None:
                raise AssertionError("로그아웃 버튼이 사용자 세션을 지우지 못했습니다.")

    def measure_demo_start(self) -> None:
        app = self.new_auth_app()
        for _ in range(REPEAT_COUNT):
            self.click(app, "데모 계정 시작", label="데모 계정으로 바로 시작")
            self.click(app, "데모 후 로그아웃", label="로그아웃", record=False)

    def measure_availability_checks(self) -> None:
        app = self.new_auth_app()
        self.text_input(app, "signup_email").input("available-latency@example.com")
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "이메일 중복 확인",
                key="check_signup_email",
            )
        self.text_input(app, "signup_nickname").input("사용가능지연측정")
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "닉네임 중복 확인",
                key="check_signup_nickname",
            )

    def fill_signup(self, app: AppTest, index: int) -> None:
        email = f"latency-signup-{index}@example.com"
        nickname = f"가입지연측정{index}"
        self.text_input(app, "signup_email").input(email)
        self.click(
            app,
            "회원가입 준비 이메일 확인",
            key="check_signup_email",
            record=False,
        )
        self.text_input(app, "signup_nickname").input(nickname)
        self.click(
            app,
            "회원가입 준비 닉네임 확인",
            key="check_signup_nickname",
            record=False,
        )
        self.text_input(app, "signup_phone").input(f"010-4000-00{index:02d}")
        self.text_input(app, "signup_password").input(TEST_PASSWORD)
        self.text_input(app, "signup_confirm").input(TEST_PASSWORD)

    def measure_signup_and_delete(self) -> None:
        app = self.new_auth_app()
        for index in range(REPEAT_COUNT):
            self.fill_signup(app, index)
            self.click(app, "회원가입", label="회원가입")
            if app.session_state["user_id"] is None:
                raise AssertionError("회원가입 버튼이 사용자 세션을 만들지 못했습니다.")

            self.text_input(app, "delete_account_password").input(TEST_PASSWORD)
            delete_confirmation = next(
                checkbox
                for checkbox in app.checkbox
                if checkbox.label == "삭제된 데이터는 복구할 수 없음을 확인했습니다."
            )
            delete_confirmation.check().run()
            self.click(app, "계정 영구 삭제", label="계정 영구 삭제")
            if app.session_state["user_id"] is not None:
                raise AssertionError("회원탈퇴 버튼이 사용자 세션을 지우지 못했습니다.")

    def login_action_user(self, database: StoreDatabase) -> AppTest:
        email = "latency-actions@example.com"
        database.register_user(
            email,
            TEST_PASSWORD,
            "버튼지연측정",
            "010-3333-4444",
        )
        app = self.new_auth_app()
        self.text_input(app, "login_email").input(email)
        self.text_input(app, "login_password").input(TEST_PASSWORD)
        self.click(app, "동작 측정 준비 로그인", label="로그인", record=False)
        return app

    def measure_profile_save(self, app: AppTest) -> None:
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "AI 추천 취향 저장",
                label="추천 취향 저장",
            )
        for _ in range(REPEAT_COUNT):
            self.text_input(app, "header_profile_password").input(
                TEST_PASSWORD
            )
            self.click(
                app,
                "프로필 비밀번호 확인",
                label="비밀번호 확인",
            )
            if not app.session_state["header_profile_verified"]:
                raise AssertionError(
                    "현재 비밀번호 확인 후 프로필 편집 화면이 열리지 않았습니다."
                )
            self.click(
                app,
                "계정 정보 저장",
                label="계정 정보 저장",
            )
            if app.session_state["header_profile_verified"]:
                raise AssertionError(
                    "계정 정보 저장 후 비밀번호 확인 상태가 초기화되지 않았습니다."
                )

    def measure_product_detail(self, app: AppTest) -> None:
        detail_key = f"shop_page_0_detail_{DETAIL_PRODUCT_ID}"
        original_nickname = app.session_state["nickname"]
        for _ in range(REPEAT_COUNT):
            self.click(app, "상품 상세", key=detail_key)
            self.click(app, "상세에서 돌아가기", key="detail_back")
            if app.session_state["user_id"] is None:
                raise AssertionError(
                    "상품 상세에서 돌아간 뒤 로그인 세션이 사라졌습니다."
                )
            if app.session_state["nickname"] != original_nickname:
                raise AssertionError(
                    "상품 상세에서 돌아간 뒤 닉네임 상태가 바뀌었습니다."
                )

        self.click(app, "상세 동작 준비", key=detail_key, record=False)
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "상세 찜 토글",
                key=f"detail_favorite_{DETAIL_PRODUCT_ID}",
            )
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "상세 장바구니 담기",
                key=f"detail_cart_{DETAIL_PRODUCT_ID}",
            )
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "상세 바로 모의결제",
                key=f"detail_buy_{DETAIL_PRODUCT_ID}",
            )
        self.click(
            app,
            "상세 동작 종료",
            key="detail_back",
            record=False,
        )

    def measure_favorite(self, app: AppTest) -> None:
        favorite_key = f"shop_page_0_favorite_{PRODUCT_ID}"
        for _ in range(REPEAT_COUNT):
            self.click(app, "찜 토글", key=favorite_key)

    def measure_add_and_delete_cart(self, app: AppTest) -> None:
        cart_key = f"shop_page_0_cart_{PRODUCT_ID}"
        for _ in range(REPEAT_COUNT):
            self.click(app, "장바구니 담기", key=cart_key)

        for quantity in range(6, 11):
            quantity_input = next(
                field
                for field in app.number_input
                if field.key == f"quantity_{PRODUCT_ID}"
            )
            started_at = perf_counter()
            quantity_input.set_value(quantity).run()
            elapsed_seconds = perf_counter() - started_at
            self.samples["장바구니 수량 변경"].append(elapsed_seconds)
            print(
                f"장바구니 수량 변경 "
                f"#{len(self.samples['장바구니 수량 변경'])}: "
                f"{elapsed_seconds:.3f}s"
            )
            if int(app.session_state["cart"][PRODUCT_ID]) != quantity:
                raise AssertionError("화면의 장바구니 수량이 즉시 갱신되지 않았습니다.")

        self.click(
            app,
            "장바구니 삭제 준비",
            key=f"delete_{PRODUCT_ID}",
            record=False,
        )
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "장바구니 삭제 준비",
                key=cart_key,
                record=False,
            )
            self.click(app, "장바구니 삭제", key=f"delete_{PRODUCT_ID}")

    def measure_checkout_and_continue(self, app: AppTest) -> None:
        cart_key = f"shop_page_0_cart_{PRODUCT_ID}"
        for _ in range(REPEAT_COUNT):
            self.click(
                app,
                "모의 주문 준비",
                key=cart_key,
                record=False,
            )
            self.click(app, "모의 주문 완료", label="모의 주문 완료")
            if app.session_state["last_order"] is None:
                raise AssertionError("모의 주문 버튼이 주문 결과를 만들지 못했습니다.")
            self.click(app, "새 쇼핑 계속하기", label="새 쇼핑 계속하기")

    def print_summary(self) -> bool:
        print("\nBUTTON LATENCY SUMMARY")
        print(
            f"budget={RESPONSE_BUDGET_SECONDS:.1f}s, "
            f"repetitions={REPEAT_COUNT}"
        )
        passed = True
        for action, samples in self.samples.items():
            action_passed = (
                len(samples) == REPEAT_COUNT
                and max(samples) < RESPONSE_BUDGET_SECONDS
            )
            passed = passed and action_passed
            status = "PASS" if action_passed else "FAIL"
            formatted = ", ".join(f"{sample:.3f}" for sample in samples)
            print(
                f"{status:4} {action}: [{formatted}] "
                f"avg={mean(samples):.3f}s max={max(samples):.3f}s"
            )
        return passed


def main() -> int:
    if not TEST_DATABASE_URL:
        raise RuntimeError("STYLEPICK_TEST_DATABASE_URL이 필요합니다.")
    database = StoreDatabase(TEST_DATABASE_URL)
    database_name = str(database.connection_args["database"])
    if not database_name.endswith("_test"):
        raise RuntimeError("측정 DB 이름은 반드시 _test로 끝나야 합니다.")

    st.cache_data.clear()
    st.cache_resource.clear()
    reset_test_database(database)
    os.environ.update(
        DATABASE_URL=TEST_DATABASE_URL,
        RECOMMENDER_BACKEND="cnn",
        STYLEPICK_TEST_SYNC_STARTUP="1",
    )

    run = ButtonLatencyRun()
    run.measure_login_and_logout(database)
    run.measure_demo_start()
    run.measure_availability_checks()
    run.measure_signup_and_delete()
    app = run.login_action_user(database)
    run.measure_profile_save(app)
    run.measure_product_detail(app)
    run.measure_favorite(app)
    run.measure_add_and_delete_cart(app)
    run.measure_checkout_and_continue(app)
    return 0 if run.print_summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
