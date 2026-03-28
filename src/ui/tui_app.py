"""
TextRPGApp — Textual 메인 애플리케이션 클래스.

브릿지 초기화, 화면 전환, 게임 시작/로드를 조율한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Static

from ..bridge.genspark_bridge import GensparkBridge
from ..engine.game_engine import GameEngine
from .screens import (
    GameScreen,
    LoadingScreen,
    SaveLoadScreen,
    SetupScreen,
    TitleScreen,
)

if TYPE_CHECKING:
    from ..engine.models import Character, WorldSetting
    from ..engine.response_parser import GameResponse


class TextRPGApp(App):
    """Text RPG 메인 Textual 애플리케이션."""

    CSS_PATH = str(Path(__file__).parent / "styles.tcss")
    TITLE = "Text RPG Engine"
    SUB_TITLE = "AI-Powered Text Adventure"

    BINDINGS = [
        ("f1", "show_help", "도움말"),
        ("f5", "save_game", "저장"),
        ("f9", "load_game", "불러오기"),
        ("escape", "toggle_menu", "메뉴"),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.config = config
        self.bridge: GensparkBridge | None = None
        self.engine: GameEngine | None = None

    # ── 마운트 ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static("")  # 초기 로딩 화면이 즉시 push되므로 빈 내용

    async def on_mount(self) -> None:
        """앱 마운트 시 로딩 화면을 표시하고 브릿지를 초기화한다."""
        await self.push_screen(LoadingScreen())
        self._initialize_bridge()

    # ── 브릿지 초기화 (워커) ─────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _initialize_bridge(self) -> None:
        """백그라운드에서 GensparkBridge를 초기화한다."""
        loading: LoadingScreen | None = None
        try:
            loading = self.query_one(LoadingScreen)
        except Exception as exc:
            logger.debug("LoadingScreen 쿼리 실패: {}", exc)

        def update_loading(msg: str) -> None:
            if loading:
                try:
                    loading.update_status(msg)
                except Exception as exc:
                    logger.debug("loading.update_status 실패: {}", exc)

        try:
            update_loading("Playwright 브라우저 시작 중...")
            self.bridge = GensparkBridge(self.config)

            update_loading("Genspark 접속 중...")
            await self.bridge.initialize()

            update_loading("연결 완료! 게임을 시작합니다...")
            logger.info("브릿지 초기화 완료")

            # 타이틀 화면으로 전환
            self._switch_to_title()

        except Exception as exc:
            logger.error("브릿지 초기화 실패: {}", exc)
            self._show_init_error(str(exc))

    def _switch_to_title(self) -> None:
        """로딩 화면에서 타이틀 화면으로 전환한다."""
        try:
            self.pop_screen()  # LoadingScreen 제거
        except Exception as exc:
            logger.debug("pop_screen 실패: {}", exc)
        self.push_screen(TitleScreen())

    def _show_init_error(self, error_msg: str) -> None:
        """초기화 실패 시 에러를 표시하고 재시도 옵션을 제공한다."""
        try:
            loading = self.query_one(LoadingScreen)
            loading.update_status(
                f"[red]초기화 실패: {error_msg[:100]}[/red]\n\n"
                "[dim]Genspark 세션을 확인하거나 앱을 재시작해주세요.[/dim]\n"
                "[dim]로그: logs/app.log[/dim]"
            )
        except Exception:
            self.notify(f"초기화 실패: {error_msg}", severity="error", timeout=10)

    # ── 게임 시작 / 로드 ─────────────────────────────────────────────────────

    async def start_new_game(
        self, world: "WorldSetting", character: "Character"
    ) -> None:
        """새 게임을 시작하고 GameScreen으로 전환한다.

        SetupScreen에서 호출된다.

        Args:
            world: 선택된 세계관
            character: 생성된 캐릭터
        """
        if not self.bridge:
            self.notify("브릿지가 초기화되지 않았습니다.", severity="error")
            return

        self.engine = GameEngine(self.bridge, self.config)

        # 로딩 알림
        self.notify("게임을 시작합니다...", timeout=2)

        try:
            # SetupScreen 제거 후 GameScreen 푸시
            game_screen = GameScreen()
            self.switch_screen(game_screen)

            # 첫 응답 가져오기 (워커)
            self._start_new_game_worker(world, character)

        except Exception as exc:
            logger.error("새 게임 시작 실패: {}", exc)
            self.notify(f"게임 시작 실패: {exc}", severity="error")

    @work(exclusive=True, thread=False)
    async def _start_new_game_worker(
        self, world: "WorldSetting", character: "Character"
    ) -> None:
        """백그라운드에서 게임을 시작하고 첫 응답을 GameScreen에 표시한다."""
        assert self.engine is not None

        try:
            response = await self.engine.start_new_game(world, character)
            self._apply_first_response(response)
        except Exception as exc:
            logger.error("게임 시작 워커 오류: {}", exc)
            self.notify(f"게임 시작 오류: {exc}", severity="error")

    def _apply_first_response(self, response: "GameResponse") -> None:
        """첫 게임 응답을 GameScreen에 적용한다."""
        try:
            game_screen = self.query_one(GameScreen)
            game_screen.set_initial_response(response)
        except Exception as exc:
            logger.error("첫 응답 적용 실패: {}", exc)

    async def load_game(self, slot_name: str) -> None:
        """세이브 파일에서 게임을 불러온다.

        SaveLoadScreen에서 호출된다.

        Args:
            slot_name: 로드할 세이브 슬롯 파일 이름 (확장자 제외)
        """
        if not self.bridge:
            self.notify("브릿지가 초기화되지 않았습니다.", severity="error")
            return

        if not self.engine:
            self.engine = GameEngine(self.bridge, self.config)

        self.notify("게임을 불러오는 중...", timeout=2)
        self._load_game_worker(slot_name)

    @work(exclusive=True, thread=False)
    async def _load_game_worker(self, slot_name: str) -> None:
        """백그라운드에서 게임을 로드하고 GameScreen에 표시한다."""
        assert self.engine is not None

        try:
            response = await self.engine.load_game(slot_name)

            # GameScreen이 없으면 생성
            try:
                game_screen = self.query_one(GameScreen)
                game_screen.set_initial_response(response)
            except Exception as exc:
                logger.debug("GameScreen 쿼리 실패, 새 화면 생성: {}", exc)
                game_screen = GameScreen()
                self.switch_screen(game_screen)
                self.call_later(game_screen.set_initial_response, response)

        except FileNotFoundError:
            self.notify("세이브 파일을 찾을 수 없습니다.", severity="error")
        except Exception as exc:
            logger.error("게임 로드 워커 오류: {}", exc)
            self.notify(f"로드 오류: {exc}", severity="error")

    # ── 전역 키 바인딩 액션 ──────────────────────────────────────────────────

    def action_show_help(self) -> None:
        """F1: 도움말 (GameScreen에 있을 때만)."""
        try:
            self.query_one(GameScreen).action_show_help()
        except Exception as exc:
            logger.debug("action_show_help 실패: {}", exc)

    def action_save_game(self) -> None:
        """F5: 빠른 저장."""
        if self.engine:
            self.push_screen(SaveLoadScreen(mode="save"))

    def action_load_game(self) -> None:
        """F9: 불러오기."""
        self.push_screen(SaveLoadScreen(mode="load"))

    def action_toggle_menu(self) -> None:
        """ESC: 일시 정지 메뉴."""
        try:
            self.query_one(GameScreen).action_toggle_menu()
        except Exception as exc:
            logger.debug("action_toggle_menu 실패: {}", exc)

    # ── 앱 종료 ─────────────────────────────────────────────────────────────

    async def on_unmount(self) -> None:
        """앱 종료 시 브릿지를 닫는다."""
        if self.bridge:
            try:
                await self.bridge.close()
            except Exception as exc:
                logger.warning("브릿지 종료 중 오류: {}", exc)
