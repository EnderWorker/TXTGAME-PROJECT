"""
Genspark 로그인 세션 관리 모듈.

Playwright의 storage_state() API로 쿠키+로컬스토리지를 JSON 파일에
저장하고 복원하여 매번 로그인하지 않아도 세션을 유지한다.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page

from .selectors import GensparkSelectors


class SessionManager:
    """브라우저 세션(쿠키 + 스토리지)을 파일로 저장하고 복원한다."""

    def __init__(self, cookie_path: str) -> None:
        """
        Args:
            cookie_path: 세션 JSON 파일 경로 (예: saves/genspark_session.json)
        """
        self._path = Path(cookie_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── 공개 메서드 ──────────────────────────────────────────────────────────

    async def save_session(self, context: BrowserContext) -> None:
        """현재 브라우저 컨텍스트의 쿠키와 스토리지를 파일로 저장한다.

        Playwright의 storage_state() 메서드를 사용하여 JSON으로 직렬화한다.

        Args:
            context: 저장할 Playwright BrowserContext
        """
        try:
            await context.storage_state(path=str(self._path))
            logger.info("세션 저장 완료: {}", self._path)
        except Exception as exc:
            logger.error("세션 저장 실패: {}", exc)
            raise

    async def load_session(self, browser: Browser) -> BrowserContext:
        """저장된 세션으로 브라우저 컨텍스트를 복원한다.

        저장된 파일이 없거나 손상된 경우 빈 컨텍스트를 반환한다.

        Args:
            browser: Playwright Browser 인스턴스

        Returns:
            세션이 적용된 BrowserContext
        """
        if self.has_saved_session():
            logger.info("저장된 세션 로드 시도: {}", self._path)
            try:
                context = await browser.new_context(
                    storage_state=str(self._path),
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                logger.info("저장된 세션으로 컨텍스트 생성 완료")
                return context
            except Exception as exc:
                logger.warning("세션 로드 실패 (새 컨텍스트로 대체): {}", exc)
                # 손상된 세션 파일 삭제
                self._path.unlink(missing_ok=True)

        logger.info("저장된 세션 없음 — 새 컨텍스트 생성")
        return await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    def has_saved_session(self) -> bool:
        """저장된 세션 파일이 존재하는지 확인한다."""
        return self._path.exists() and self._path.stat().st_size > 50

    async def is_session_valid(self, page: Page) -> bool:
        """현재 페이지에서 로그인 상태인지 확인한다.

        LOGGED_IN_INDICATOR 셀렉터로 로그인 완료 요소가 있는지 검사한다.
        여러 후보 셀렉터를 순서대로 시도한다.

        Args:
            page: 확인할 Playwright Page

        Returns:
            로그인 상태이면 True
        """
        candidates = [
            s.strip()
            for s in GensparkSelectors.LOGGED_IN_INDICATOR.split(",")
            if s.strip()
        ]
        for sel in candidates:
            try:
                element = await page.wait_for_selector(sel, timeout=3_000)
                if element:
                    logger.debug("로그인 확인 셀렉터 히트: '{}'", sel)
                    return True
            except Exception:
                continue

        logger.debug("로그인 상태 확인 실패 — 모든 셀렉터 미일치")
        return False

    def delete_session(self) -> None:
        """저장된 세션 파일을 삭제한다 (재로그인 강제 시 사용)."""
        if self._path.exists():
            self._path.unlink()
            logger.info("세션 파일 삭제: {}", self._path)
