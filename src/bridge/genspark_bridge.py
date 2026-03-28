"""
Genspark Bridge 핵심 모듈.

Playwright async API로 chat.genspark.ai와 headless 통신.
- 세션 자동 저장/복원
- 로그인 안 되어 있으면 headless=False로 전환 후 수동 로그인 유도
- 사람처럼 타이핑 시뮬레이션
- 텍스트 안정화 방식으로 응답 완료 감지
- 모든 셀렉터 실패에 대한 상세 로그
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from .selectors import GensparkSelectors
from .session_manager import SessionManager

Path("logs").mkdir(exist_ok=True)


class BridgeError(Exception):
    """GensparkBridge 전용 예외."""


class GensparkBridge:
    """
    chat.genspark.ai 웹 UI와 프로그래밍적으로 통신하는 브릿지.

    사용 예::

        bridge = GensparkBridge(config)
        await bridge.initialize()
        response = await bridge.send_message("안녕하세요!")
        await bridge.close()
    """

    def __init__(self, config: dict) -> None:
        """
        Args:
            config: settings.toml 전체를 toml.load()한 딕셔너리
        """
        self._cfg_g: dict = config.get("genspark", {})
        self._cfg_s: dict = config.get("session", {})
        self._cfg_l: dict = config.get("logging", {})

        self._base_url: str = self._cfg_g.get("base_url", "https://chat.genspark.ai")
        self._headless: bool = self._cfg_g.get("headless", True)
        self._input_delay_min: float = self._cfg_g.get("input_delay_min", 0.03)
        self._input_delay_max: float = self._cfg_g.get("input_delay_max", 0.08)
        self._response_timeout: float = self._cfg_g.get("response_timeout", 120)
        self._stable_duration: float = self._cfg_g.get("response_stable_duration", 3)

        cookie_file = self._cfg_s.get("cookie_file", "saves/genspark_session.json")
        self._session_manager = SessionManager(cookie_file)
        self._auto_save: bool = self._cfg_s.get("auto_save", True)

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self._setup_logging()
        logger.debug("GensparkBridge 생성 (headless={})", self._headless)

    # ── 초기화 / 종료 ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """브라우저를 시작하고 Genspark에 로그인 상태를 보장한다.

        1. Playwright 인스턴스 시작
        2. SessionManager로 저장된 세션 복원 시도
        3. chat.genspark.ai 접속
        4. 로그인 상태 확인 → 필요 시 수동 로그인 유도 및 세션 저장
        5. 기본 모델 선택
        """
        logger.info("=== GensparkBridge 초기화 시작 ===")

        self._playwright = await async_playwright().start()
        await self._launch_browser(self._headless)

        assert self._browser is not None
        self._context = await self._session_manager.load_session(self._browser)
        self._page = await self._context.new_page()

        logger.info("Genspark 접속 중: {}", self._base_url)
        await self._page.goto(self._base_url, wait_until="networkidle", timeout=30_000)

        await self.ensure_logged_in(self._page)

        default_model = self._cfg_g.get("default_model", "")
        if default_model:
            ok = await self.select_model(default_model)
            if not ok:
                logger.warning("기본 모델 '{}' 선택 실패 — 계속 진행", default_model)

        logger.info("=== GensparkBridge 초기화 완료 ===")

    async def ensure_logged_in(self, page: Page) -> None:
        """로그인 상태를 확인하고 필요하면 수동 로그인을 유도한다.

        로그인이 안 된 경우:
        - headless였으면 headless=False로 브라우저를 다시 열기
        - 콘솔에 로그인 안내 출력
        - 사용자가 로그인하면 세션 저장

        Args:
            page: 확인할 Playwright Page
        """
        if await self._session_manager.is_session_valid(page):
            logger.info("로그인 상태 확인 완료")
            return

        logger.warning("로그인 상태 아님 — 수동 로그인이 필요합니다")

        if self._headless:
            logger.info("headless=False로 브라우저 재시작")
            await self._restart_browser(headless=False)
            page = self._page
            assert page is not None
            await page.goto(self._base_url, wait_until="networkidle", timeout=30_000)

        print("\n" + "=" * 60)
        print("  ===== Genspark 로그인이 필요합니다 =====")
        print("  브라우저에서 로그인을 완료한 후")
        print("  이 터미널에서 Enter를 눌러주세요.")
        print("=" * 60)

        await asyncio.get_event_loop().run_in_executor(
            None, input, "  → 로그인 완료 후 Enter: "
        )

        if not await self._session_manager.is_session_valid(page):
            raise BridgeError("로그인 확인 실패 — LOGGED_IN_INDICATOR를 감지하지 못했습니다.")

        if self._auto_save:
            assert self._context is not None
            await self._session_manager.save_session(self._context)
            logger.info("로그인 완료 및 세션 저장")

        # 원래 headless 모드였으면 headless=True로 복원 (선택적)
        # 게임 플레이 시에는 headless 유지가 더 자연스러우므로 재시작하지 않음

    async def close(self) -> None:
        """세션을 저장하고 브라우저를 종료한다."""
        logger.info("GensparkBridge 종료 중...")
        try:
            if self._auto_save and self._context:
                await self._session_manager.save_session(self._context)
        except Exception as exc:
            logger.warning("종료 중 세션 저장 실패: {}", exc)
        finally:
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            self._context = None
            self._browser = None
            self._playwright = None
            self._page = None
        logger.info("GensparkBridge 종료 완료")

    # ── 채팅 기능 ────────────────────────────────────────────────────────────

    async def send_message(self, message: str) -> str:
        """메시지를 전송하고 AI 응답을 반환한다.

        1. _find_element()로 채팅 입력란 찾기
        2. 입력란 클릭 및 기존 텍스트 클리어 (Ctrl+A, Delete)
        3. _human_like_type()로 메시지 타이핑
        4. Enter 키 전송 (Send 버튼 클릭 fallback)
        5. _wait_for_response_complete()로 응답 대기
        6. 완성된 응답 텍스트 반환

        Args:
            message: 전송할 메시지 문자열

        Returns:
            AI 응답 텍스트

        Raises:
            BridgeError: 입력란을 찾지 못하거나 응답 수신 실패
        """
        assert self._page is not None, "initialize()를 먼저 호출하세요."
        short = message[:60] + ("..." if len(message) > 60 else "")
        logger.info("메시지 전송: '{}'", short)

        # 채팅 입력란 찾기
        input_locator = await self._find_element(
            GensparkSelectors.CHAT_INPUT, label="CHAT_INPUT", timeout=10.0
        )

        # 클릭 후 기존 텍스트 클리어
        await input_locator.click()
        await self._page.keyboard.press("Control+a")
        await self._page.keyboard.press("Delete")
        await asyncio.sleep(0.2)

        # 사람처럼 타이핑
        await self._human_like_type(input_locator, message)
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # Enter 키로 전송 (실패 시 버튼 클릭)
        try:
            await self._page.keyboard.press("Enter")
            logger.debug("Enter 키로 전송")
        except Exception as e:
            logger.debug("Enter 키 실패 ({}), 전송 버튼 시도", e)
            send_locator = await self._find_element(
                GensparkSelectors.SEND_BUTTON, label="SEND_BUTTON", timeout=5.0
            )
            await send_locator.click()
            logger.debug("전송 버튼 클릭으로 전송")

        # 응답 완료 대기
        response = await self._wait_for_response_complete()
        logger.info("응답 수신 완료 ({}자)", len(response))
        return response

    async def start_new_conversation(self) -> None:
        """새 대화를 시작한다.

        NEW_CHAT_BUTTON 클릭 시도, 실패 시 base_url로 직접 이동.
        """
        assert self._page is not None
        logger.info("새 대화 시작")

        try:
            btn = await self._find_element(
                GensparkSelectors.NEW_CHAT_BUTTON,
                label="NEW_CHAT_BUTTON",
                timeout=5.0,
            )
            await btn.click()
            await self._page.wait_for_load_state("networkidle", timeout=15_000)
            logger.debug("새 대화 버튼 클릭 성공")
        except Exception as exc:
            logger.warning("새 대화 버튼 실패 ({}), base_url로 이동", exc)
            await self._page.goto(self._base_url, wait_until="networkidle", timeout=30_000)

        await asyncio.sleep(random.uniform(0.8, 1.5))

    async def select_model(self, model_name: str) -> bool:
        """모델 선택 드롭다운에서 원하는 모델을 선택한다.

        Args:
            model_name: 선택할 모델 이름 (예: "Claude Sonnet")

        Returns:
            성공이면 True, 실패이면 False
        """
        assert self._page is not None
        logger.info("모델 선택 시도: '{}'", model_name)

        try:
            selector_btn = await self._find_element(
                GensparkSelectors.MODEL_SELECTOR_BUTTON,
                label="MODEL_SELECTOR_BUTTON",
                timeout=5.0,
            )
            await selector_btn.click()
            await asyncio.sleep(0.5)

            # 텍스트 검색으로 모델 옵션 찾기
            option = await self._find_element_by_text(model_name, timeout=5.0)
            if option is None:
                option = await self._find_model_option_by_text(model_name)

            await option.click()
            await asyncio.sleep(0.5)
            logger.info("모델 '{}' 선택 완료", model_name)
            return True

        except Exception as exc:
            logger.warning("모델 선택 실패 ('{}'): {}", model_name, exc)
            return False

    async def get_last_response(self) -> str:
        """현재 대화에서 마지막 AI 응답 텍스트를 반환한다.

        RESPONSE_CONTAINER 전체를 찾은 뒤 마지막 것의 RESPONSE_TEXT를 반환한다.

        Returns:
            마지막 응답 텍스트 (없으면 빈 문자열)
        """
        assert self._page is not None

        try:
            # JS로 마지막 응답 컨테이너 내부의 텍스트 추출
            text: str = await self._page.evaluate("""
                () => {
                    // RESPONSE_CONTAINER 후보 셀렉터들
                    const containerSelectors = [
                        "div[class*='message'][class*='assistant']",
                        "div[class*='response']",
                        "div[class*='answer']"
                    ];
                    // RESPONSE_TEXT 후보 셀렉터들
                    const textSelectors = [
                        "div[class*='markdown']",
                        "div[class*='prose']",
                        "div[class*='content']"
                    ];

                    for (const cSel of containerSelectors) {
                        const containers = document.querySelectorAll(cSel);
                        if (containers.length > 0) {
                            const last = containers[containers.length - 1];
                            for (const tSel of textSelectors) {
                                const textEl = last.querySelector(tSel);
                                if (textEl) {
                                    return textEl.innerText || textEl.textContent || '';
                                }
                            }
                            // 텍스트 요소 못 찾으면 컨테이너 자체 텍스트
                            return last.innerText || last.textContent || '';
                        }
                    }
                    return '';
                }
            """)
            return (text or "").strip()
        except Exception as exc:
            logger.warning("마지막 응답 추출 실패: {}", exc)
            return ""

    async def debug_screenshot(self, name: str = "debug") -> str:
        """현재 페이지 스크린샷을 logs/ 에 저장한다.

        Args:
            name: 파일명 접두사

        Returns:
            저장된 파일 경로
        """
        assert self._page is not None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"logs/{name}_{ts}.png"
        Path("logs").mkdir(exist_ok=True)
        await self._page.screenshot(path=path, full_page=True)
        logger.info("스크린샷 저장: {}", path)
        return path

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────────

    async def _find_element(
        self,
        selectors: str,
        label: str = "",
        timeout: float = 10.0,
    ) -> Locator:
        """쉼표로 구분된 CSS 셀렉터를 순서대로 시도하여 Locator를 반환한다.

        각 셀렉터를 timeout / 후보수 만큼의 시간으로 시도한다.
        모두 실패하면 스크린샷을 찍고 상세 에러 로그를 남긴 뒤 예외를 발생시킨다.

        Args:
            selectors: 쉼표 구분 CSS 셀렉터 문자열
            label: 로그용 이름
            timeout: 전체 허용 시간 (초)

        Returns:
            찾은 Locator

        Raises:
            BridgeError: 모든 셀렉터 실패 시
        """
        assert self._page is not None
        candidates = [s.strip() for s in selectors.split(",") if s.strip()]
        per_ms = int(timeout * 1000 / max(len(candidates), 1))
        tried: list[str] = []

        for sel in candidates:
            tried.append(sel)
            try:
                locator = self._page.locator(sel).first
                await locator.wait_for(state="visible", timeout=per_ms)
                logger.debug("[{}] 셀렉터 히트: '{}'", label, sel)
                return locator
            except Exception as exc:
                logger.debug("[{}] 셀렉터 실패: '{}' → {}", label, sel, type(exc).__name__)

        # 모두 실패 — 스크린샷 + 상세 로그
        try:
            await self.debug_screenshot(f"selector_fail_{label}")
        except Exception:
            pass

        tried_str = "\n".join(f"  - {s}" for s in tried)
        raise BridgeError(
            f"[{label}] 모든 셀렉터 실패 (timeout={timeout}s).\n"
            f"시도한 셀렉터 목록:\n{tried_str}\n"
            "→ src/bridge/selectors.py 에서 해당 셀렉터를 수정하세요."
        )

    async def _find_element_by_text(
        self, text: str, timeout: float = 5.0
    ) -> Optional[Locator]:
        """페이지에서 특정 텍스트가 포함된 첫 번째 요소를 반환한다.

        Args:
            text: 찾을 텍스트
            timeout: 대기 시간 (초)

        Returns:
            찾으면 Locator, 없으면 None
        """
        assert self._page is not None
        try:
            locator = self._page.get_by_text(text, exact=False).first
            await locator.wait_for(state="visible", timeout=int(timeout * 1000))
            return locator
        except Exception:
            return None

    async def _find_model_option_by_text(self, model_name: str) -> Locator:
        """MODEL_OPTION 셀렉터 내에서 model_name 텍스트가 포함된 요소를 찾는다.

        Args:
            model_name: 찾을 모델 이름

        Returns:
            찾은 Locator

        Raises:
            BridgeError: 찾지 못한 경우
        """
        assert self._page is not None
        candidates = [s.strip() for s in GensparkSelectors.MODEL_OPTION.split(",")]

        for sel in candidates:
            try:
                elements = await self._page.query_selector_all(sel)
                for el in elements:
                    inner = (await el.inner_text()).strip()
                    if model_name.lower() in inner.lower():
                        logger.debug("모델 옵션 발견: '{}' in '{}'", model_name, inner)
                        # ElementHandle을 Locator로 변환
                        return self._page.locator(sel).filter(has_text=model_name).first
            except Exception as exc:
                logger.debug("MODEL_OPTION '{}' 탐색 실패: {}", sel, exc)

        raise BridgeError(f"모델 옵션 '{model_name}'을 찾지 못했습니다.")

    async def _human_like_type(self, locator: Locator, text: str) -> None:
        """사람처럼 한 글자씩 랜덤 딜레이로 타이핑한다.

        Args:
            locator: 타이핑할 입력 요소 Locator
            text: 입력할 텍스트
        """
        await locator.click()
        for char in text:
            await locator.press_sequentially(char, delay=0)
            await asyncio.sleep(
                random.uniform(self._input_delay_min, self._input_delay_max)
            )
        logger.debug("타이핑 완료 ({}자)", len(text))

    async def _wait_for_response_complete(self) -> str:
        """응답 스트리밍이 완료될 때까지 대기하고 최종 텍스트를 반환한다.

        동작 방식:
        1. 1~2초 초기 대기 (응답이 나타나기 시작할 시간)
        2. 마지막 RESPONSE_CONTAINER의 innerText를 0.5초 간격으로 폴링
        3. stable_duration 초 동안 텍스트 변화 없으면 완료 판단
        4. response_timeout 초 초과 시 현재 텍스트 반환 + 경고 로그

        Returns:
            완성된 응답 텍스트 (timeout 시 중간 텍스트)
        """
        logger.debug(
            "응답 대기 시작 (timeout={}s, stable={}s)",
            self._response_timeout,
            self._stable_duration,
        )

        poll_interval = 0.5
        stable_count_needed = max(1, int(self._stable_duration / poll_interval))
        stable_count = 0
        last_text = ""
        elapsed = 0.0

        # 응답이 나타나기를 짧게 대기
        await asyncio.sleep(random.uniform(1.0, 2.0))

        while elapsed < self._response_timeout:
            current_text = await self.get_last_response()

            if current_text and current_text == last_text:
                stable_count += 1
                if stable_count >= stable_count_needed:
                    logger.debug("응답 완료 감지 (안정화 {}회)", stable_count)
                    return current_text
            else:
                if current_text != last_text:
                    logger.debug(
                        "텍스트 변화 ({}자 → {}자)",
                        len(last_text),
                        len(current_text),
                    )
                stable_count = 0
                last_text = current_text

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "응답 timeout ({}s) — 현재까지 텍스트 반환 ({}자)",
            self._response_timeout,
            len(last_text),
        )
        return last_text

    async def _launch_browser(self, headless: bool) -> None:
        """Playwright로 Chromium을 실행한다.

        Args:
            headless: True면 백그라운드, False면 화면에 표시
        """
        assert self._playwright is not None
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        logger.debug("브라우저 시작 (headless={})", headless)

    async def _restart_browser(self, headless: bool) -> None:
        """브라우저를 종료하고 새 headless 설정으로 재시작한다.

        Args:
            headless: 재시작할 headless 모드
        """
        logger.info("브라우저 재시작 (headless={})", headless)

        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

        await self._launch_browser(headless)

        assert self._browser is not None
        self._context = await self._session_manager.load_session(self._browser)
        self._page = await self._context.new_page()

    def _setup_logging(self) -> None:
        """loguru 로거를 파일(DEBUG)·콘솔(INFO) 두 채널로 설정한다."""
        log_level: str = self._cfg_l.get("level", "DEBUG")
        log_file: str = self._cfg_l.get("file", "logs/app.log")
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        logger.remove()

        # 콘솔 — INFO 이상
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            colorize=True,
        )
        # 파일 — DEBUG 이상, 10MB 롤오버
        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} | {message}",
            rotation="10 MB",
            encoding="utf-8",
        )
        logger.debug("로깅 설정 완료 (level={}, file={})", log_level, log_file)
