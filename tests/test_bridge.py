"""
GensparkBridge 통합 테스트.

직접 실행 가능한 스크립트 (pytest 불필요).
실제 Genspark 세션이 필요하므로 반드시 인터넷 연결 상태에서 실행한다.

실행:
    python tests/test_bridge.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 모듈 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toml

from src.bridge.genspark_bridge import GensparkBridge


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def _fail(msg: str) -> None:
    print(f"  ❌  {msg}")


async def test_bridge_basic() -> None:
    """기본 Bridge 동작 테스트.

    1. GensparkBridge 초기화 (headless=False 권장)
    2. 로그인 확인
    3. 새 대화 시작
    4. 첫 번째 메시지 전송 및 응답 수신
    5. 다중 턴 두 번째 메시지 전송
    6. 종료
    """
    config = toml.load("config/settings.toml")
    # 테스트용으로 headless=False 오버라이드
    config["genspark"]["headless"] = False

    bridge = GensparkBridge(config)

    _section("1. GensparkBridge 초기화")
    try:
        await bridge.initialize()
        _ok("초기화 및 로그인 완료")
    except Exception as exc:
        _fail(f"초기화 실패: {exc}")
        await _screenshot(bridge, "test_init_fail")
        await bridge.close()
        return

    _section("2. 새 대화 시작")
    try:
        await bridge.start_new_conversation()
        _ok("새 대화 시작")
    except Exception as exc:
        _fail(f"새 대화 실패: {exc}")
        await _screenshot(bridge, "test_new_conv_fail")

    _section("3. 첫 번째 메시지 전송")
    msg1 = "안녕하세요, 간단히 자기소개를 해주세요."
    print(f"  전송: {msg1}")
    try:
        resp1 = await bridge.send_message(msg1)
        assert len(resp1) > 0, "응답이 비어 있습니다"
        _ok(f"응답 수신 ({len(resp1)}자)")
        print(f"\n  [응답 미리보기]\n  {resp1[:200]}...\n")
    except Exception as exc:
        _fail(f"첫 메시지 실패: {exc}")
        await _screenshot(bridge, "test_msg1_fail")
        await bridge.close()
        return

    _section("4. 두 번째 메시지 (다중 턴 테스트)")
    msg2 = "감사합니다. 오늘 날씨는 어떤가요?"
    print(f"  전송: {msg2}")
    try:
        resp2 = await bridge.send_message(msg2)
        assert len(resp2) > 0, "응답이 비어 있습니다"
        _ok(f"응답 수신 ({len(resp2)}자)")
        print(f"\n  [응답 미리보기]\n  {resp2[:200]}...\n")
    except Exception as exc:
        _fail(f"두 번째 메시지 실패: {exc}")
        await _screenshot(bridge, "test_msg2_fail")

    _section("5. 종료")
    try:
        await bridge.close()
        _ok("정상 종료")
    except Exception as exc:
        _fail(f"종료 오류: {exc}")

    print(f"\n{'=' * 60}")
    print("  test_bridge_basic 완료")
    print(f"{'=' * 60}\n")


async def test_new_conversation() -> None:
    """새 대화 시작이 정상 동작하는지 테스트한다."""
    config = toml.load("config/settings.toml")
    config["genspark"]["headless"] = False
    bridge = GensparkBridge(config)

    _section("test_new_conversation")
    try:
        await bridge.initialize()
        _ok("초기화 완료")

        for i in range(2):
            await bridge.start_new_conversation()
            _ok(f"새 대화 {i + 1} 시작")

    except Exception as exc:
        _fail(f"테스트 실패: {exc}")
        await _screenshot(bridge, "test_new_conv")
    finally:
        await bridge.close()


async def test_session_persistence() -> None:
    """세션 저장 후 재로드하여 로그인이 유지되는지 테스트한다."""
    config = toml.load("config/settings.toml")
    config["genspark"]["headless"] = False

    _section("test_session_persistence — 1차 실행 (세션 저장)")
    bridge1 = GensparkBridge(config)
    try:
        await bridge1.initialize()
        _ok("1차 초기화 및 로그인 완료")
    finally:
        await bridge1.close()
        _ok("1차 종료 (세션 저장 완료)")

    _section("test_session_persistence — 2차 실행 (세션 재사용)")
    bridge2 = GensparkBridge(config)
    try:
        await bridge2.initialize()
        _ok("저장된 세션으로 재로그인 성공")
    except Exception as exc:
        _fail(f"세션 재사용 실패: {exc}")
        await _screenshot(bridge2, "test_session_reuse_fail")
    finally:
        await bridge2.close()


async def _screenshot(bridge: GensparkBridge, name: str) -> None:
    """실패 시 스크린샷을 안전하게 저장한다."""
    try:
        path = await bridge.debug_screenshot(name)
        print(f"  📸 스크린샷: {path}")
    except Exception:
        pass


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  GensparkBridge 통합 테스트")
    print("=" * 60)

    # 실행할 테스트 선택
    print("\n실행할 테스트를 선택하세요:")
    print("  1. test_bridge_basic (기본 동작)")
    print("  2. test_new_conversation (새 대화)")
    print("  3. test_session_persistence (세션 유지)")
    print("  4. 전체 실행")

    choice = input("\n선택 (1-4, 기본값 1): ").strip() or "1"

    async def run_selected() -> None:
        if choice == "1":
            await test_bridge_basic()
        elif choice == "2":
            await test_new_conversation()
        elif choice == "3":
            await test_session_persistence()
        elif choice == "4":
            await test_bridge_basic()
            await test_new_conversation()
            await test_session_persistence()
        else:
            await test_bridge_basic()

    asyncio.run(run_selected())
