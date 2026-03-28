"""
Text RPG Textual 스크린 모음.

TitleScreen, SetupScreen, GameScreen, SaveLoadScreen, GameOverScreen,
LoadingScreen을 정의한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    OptionList,
    Static,
)

from .widgets import ChoicePanel, GameInput, HPBar, NarrativeLog, StatPanel

if TYPE_CHECKING:
    from ..engine.game_engine import GameEngine
    from ..engine.models import Character, WorldSetting
    from ..engine.response_parser import GameResponse


# ASCII 아트 타이틀
_ASCII_TITLE = r"""
 _______ __   __ _______ ______
|__   __|\ \ / /|__   __|  ____|
   | |    \ V /    | |  | |__
   | |     > <     | |  |  __|
   | |    / . \    | |  | |
   |_|   /_/ \_\   |_|  |_|
 ______  _____   _____
|  __  ||  __ \ / ____|
| |__) || |__) | |  __
|  _  / |  ___/| | |_ |
| | \ \ | |    | |__| |
|_|  \_\|_|     \_____|
"""


# ═══════════════════════════════════════════════════════════════
# 로딩 화면
# ═══════════════════════════════════════════════════════════════

class LoadingScreen(Screen):
    """브릿지 초기화 중 표시되는 로딩 화면."""

    CSS_PATH = "styles.tcss"

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Text RPG Engine[/bold]", id="loading-text"),
            Static("AI 게임 마스터 연결 중...", id="loading-detail"),
            id="loading-container",
        )

    def update_status(self, message: str) -> None:
        """로딩 상태 메시지를 업데이트한다."""
        try:
            self.query_one("#loading-detail", Static).update(message)
        except Exception as exc:
            logger.debug("loading-detail 업데이트 실패: {}", exc)


# ═══════════════════════════════════════════════════════════════
# 타이틀 화면
# ═══════════════════════════════════════════════════════════════

class TitleScreen(Screen):
    """게임 타이틀 화면."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("n", "new_game", "새 게임"),
        ("l", "load_game", "불러오기"),
        ("q", "quit_game", "종료"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static(_ASCII_TITLE, id="ascii-title"),
            Static("AI-Powered Text Adventure", id="subtitle"),
            Vertical(
                Button("  새 게임 시작  [N]", id="btn-new", variant="primary", classes="title-btn"),
                Button("  불러오기  [L]", id="btn-load", classes="title-btn"),
                Button("  종료  [Q]", id="btn-quit", classes="title-btn"),
                id="title-menu",
            ),
            id="title-container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-new":
                self.action_new_game()
            case "btn-load":
                self.action_load_game()
            case "btn-quit":
                self.action_quit_game()

    def action_new_game(self) -> None:
        self.app.push_screen(SetupScreen())

    def action_load_game(self) -> None:
        self.app.push_screen(SaveLoadScreen(mode="load"))

    def action_quit_game(self) -> None:
        self.app.exit()


# ═══════════════════════════════════════════════════════════════
# 설정 화면
# ═══════════════════════════════════════════════════════════════

class SetupScreen(Screen):
    """세계관 선택 및 캐릭터 생성 화면."""

    CSS_PATH = "styles.tcss"

    def __init__(self) -> None:
        super().__init__()
        self._worlds: list["WorldSetting"] = []

    def compose(self) -> ComposeResult:
        yield Static("⚔  새 게임 설정", id="setup-title")
        yield Horizontal(
            # 세계관 선택 패널
            Vertical(
                Static("세계관 선택", id="world-panel-title"),
                OptionList(id="world-list"),
                Static("", id="world-desc"),
                id="world-panel",
            ),
            # 캐릭터 패널
            Vertical(
                Static("캐릭터 설정", id="char-panel-title"),
                Static("이름", classes="field-label"),
                Input(placeholder="캐릭터 이름을 입력하세요", id="char-name", classes="field-input"),
                Static("클래스", classes="field-label"),
                Input(placeholder="예: 전사, 마법사, 해커...", id="char-class", classes="field-input"),
                Static("", id="class-hint", classes="muted-text"),
                id="char-panel",
            ),
            id="setup-body",
        )
        yield Horizontal(
            Button("뒤로", id="btn-back", classes="title-btn"),
            Button("게임 시작 ▶", id="btn-start", variant="success"),
            id="setup-buttons",
        )

    def on_mount(self) -> None:
        """세계관 목록을 로드한다."""
        from ..engine.game_engine import load_worlds
        self._worlds = load_worlds()

        world_list = self.query_one("#world-list", OptionList)
        if self._worlds:
            for w in self._worlds:
                world_list.add_option(f"{w.name}  [{w.genre}]")
        else:
            world_list.add_option("(세계관 파일을 찾을 수 없습니다)")

        # 첫 번째 항목 선택
        if self._worlds:
            self._update_world_desc(0)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """선택된 세계관의 설명을 표시한다."""
        self._update_world_desc(event.option_index)

    def _update_world_desc(self, idx: int) -> None:
        """세계관 설명 및 클래스 힌트를 업데이트한다."""
        if not self._worlds or idx >= len(self._worlds):
            return

        world = self._worlds[idx]
        desc_widget = self.query_one("#world-desc", Static)
        desc_widget.update(world.description[:200] + ("..." if len(world.description) > 200 else ""))

        # 장르에 따른 클래스 힌트
        hints = {
            "판타지": "전사 / 마법사 / 궁수 / 도적 / 성직자",
            "사이버펑크": "해커 / 사이보그 전사 / 정보 브로커 / 엔지니어",
            "좀비": "생존자 / 의사 / 군인 출신 / 기계공",
        }
        hint = ""
        for key, val in hints.items():
            if key in world.genre:
                hint = f"추천: {val}"
                break
        self.query_one("#class-hint", Static).update(f"[dim]{hint}[/dim]")
        self.query_one("#char-class", Input).placeholder = hint or "클래스를 입력하세요"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-back":
                self.app.pop_screen()
            case "btn-start":
                self._start_game()

    def _start_game(self) -> None:
        """입력값을 검증하고 게임을 시작한다."""
        from ..engine.models import Character

        # 세계관 선택 확인
        world_list = self.query_one("#world-list", OptionList)
        highlighted = world_list.highlighted
        if highlighted is None or not self._worlds:
            self.app.notify("세계관을 선택해주세요.", severity="warning")
            return

        if highlighted >= len(self._worlds):
            self.app.notify("유효한 세계관을 선택해주세요.", severity="warning")
            return

        world = self._worlds[highlighted]

        # 캐릭터 이름
        name = self.query_one("#char-name", Input).value.strip()
        if not name:
            self.app.notify("캐릭터 이름을 입력해주세요.", severity="warning")
            self.query_one("#char-name").focus()
            return

        char_class = self.query_one("#char-class", Input).value.strip() or "모험가"
        character = Character(name=name, char_class=char_class)

        # 게임 시작 — tui_app의 메서드 호출
        self.app.call_later(self.app.start_new_game, world, character)  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════
# 메인 게임 화면
# ═══════════════════════════════════════════════════════════════

class GameScreen(Screen):
    """메인 게임 플레이 화면.

    레이아웃:
    ┌─ 헤더 (위치 + 턴 수) ────────────────────────┐
    │  NarrativeLog (서사, ~55%)                   │
    │  StatPanel (상태, 오른쪽 25%)                 │
    │  ChoicePanel (선택지, ~15%)                   │
    │  GameInput (입력, ~10%)                      │
    └─ 푸터 (F1/F5/F9/ESC 안내) ──────────────────┘
    """

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("f1", "show_help", "도움말"),
        ("f5", "save_game", "저장"),
        ("f9", "load_game", "불러오기"),
        ("escape", "toggle_menu", "메뉴"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._last_choices: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            # 왼쪽: 서사 + 선택지 + 입력
            Vertical(
                NarrativeLog(id="narrative-log"),
                ChoicePanel(id="choice-panel"),
                Container(
                    GameInput(id="game-input"),
                    id="input-panel",
                ),
                id="left-panel",
            ),
            # 오른쪽: 상태 패널
            ScrollableContainer(
                StatPanel(id="stat-panel-inner"),
                id="stat-panel",
            ),
            id="game-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        """마운트 시 입력란에 포커스를 준다."""
        self.query_one(GameInput).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """플레이어가 Enter를 눌렀을 때 처리한다."""
        if event.input.id != "game-input":
            return

        action = event.value.strip()
        if not action:
            return

        game_input = self.query_one(GameInput)
        game_input.clear()
        game_input.set_loading(True)

        # 서사 로그에 플레이어 행동 표시
        narrative_log = self.query_one(NarrativeLog)
        narrative_log.add_player_action(action)

        # 백그라운드 워커로 엔진 처리
        self._process_action(action)

    @work(exclusive=True, thread=False)
    async def _process_action(self, action: str) -> None:
        """백그라운드에서 엔진 처리 후 UI를 업데이트한다.

        Args:
            action: 플레이어 입력 텍스트
        """
        engine: "GameEngine" = self.app.engine  # type: ignore[attr-defined]
        game_input = self.query_one(GameInput)

        try:
            response = await engine.process_player_action(action)
            self.update_display(response)
        except Exception as exc:
            logger.error("플레이어 행동 처리 오류: {}", exc)
            self.query_one(NarrativeLog).add_system_message(
                f"[red]오류가 발생했습니다: {exc}[/red]",
            )
        finally:
            game_input.set_ready()

    def update_display(self, response: "GameResponse") -> None:
        """게임 응답으로 UI 각 영역을 업데이트한다.

        Args:
            response: 파싱된 GameResponse
        """
        # 서사 업데이트
        if response.narrative:
            self.query_one(NarrativeLog).add_narrative(response.narrative)

        # 상태 패널 업데이트
        if response.state:
            try:
                self.query_one(StatPanel).update_stats(response.state)
            except Exception as exc:
                logger.debug("StatPanel 업데이트 실패: {}", exc)

        # 선택지 업데이트
        self._last_choices = response.choices
        self.query_one(ChoicePanel).update_choices(response.choices)

        # 헤더 업데이트 (위치 + 턴)
        self._update_header(response)

        # 게임 오버 처리
        if response.is_game_over:
            self.call_later(self._handle_game_over, response)

    def _update_header(self, response: "GameResponse") -> None:
        """헤더 서브타이틀에 현재 위치와 턴 수를 표시한다."""
        try:
            engine: "GameEngine" = self.app.engine  # type: ignore[attr-defined]
            turn = engine.state_manager.game_state.turn_count
            location = response.state.get("location", "")
            subtitle = f"턴 {turn}"
            if location:
                subtitle = f"{location}  |  턴 {turn}"
            self.query_one(Header).sub_title = subtitle
        except Exception as exc:
            logger.debug("헤더 업데이트 실패: {}", exc)

    async def _handle_game_over(self, response: "GameResponse") -> None:
        """게임 오버 화면으로 전환한다."""
        await self.app.push_screen(GameOverScreen(last_narrative=response.narrative))

    def set_initial_response(self, response: "GameResponse") -> None:
        """새 게임 시작 시 첫 응답으로 화면을 초기화한다.

        Args:
            response: 첫 번째 GameResponse
        """
        # 로그 초기화
        self.query_one(NarrativeLog).clear()
        self.update_display(response)

    # ── 키 바인딩 액션 ──────────────────────────────────────────────────────

    def action_show_help(self) -> None:
        """도움말을 표시한다."""
        self.query_one(NarrativeLog).add_system_message(
            "[bold]━━ 도움말 ━━[/bold]\n"
            "• 숫자 입력 → 해당 번호의 선택지 선택\n"
            "• 자유 텍스트 → 원하는 행동 직접 입력\n"
            "• F5 → 게임 저장\n"
            "• F9 → 게임 불러오기\n"
            "• ESC → 메뉴"
        )

    def action_save_game(self) -> None:
        """빠른 저장 (슬롯 이름 입력 없이 저장)."""
        self.app.push_screen(SaveLoadScreen(mode="save"))

    def action_load_game(self) -> None:
        """저장 목록에서 불러오기."""
        self.app.push_screen(SaveLoadScreen(mode="load"))

    def action_toggle_menu(self) -> None:
        """ESC: 타이틀로 돌아갈지 확인."""
        self.app.push_screen(PauseMenuScreen())


# ═══════════════════════════════════════════════════════════════
# 일시 정지 메뉴 (ESC)
# ═══════════════════════════════════════════════════════════════

class PauseMenuScreen(ModalScreen):
    """ESC 키로 표시되는 일시 정지 메뉴."""

    CSS_PATH = "styles.tcss"

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]━━ 일시 정지 ━━[/bold]", id="saveload-title"),
            Button("게임 저장 (F5)", id="btn-pause-save", classes="saveload-btn"),
            Button("게임 불러오기 (F9)", id="btn-pause-load", classes="saveload-btn"),
            Button("타이틀로 나가기", id="btn-pause-title", classes="saveload-btn"),
            Button("계속하기", id="btn-pause-continue", classes="saveload-btn"),
            id="saveload-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-pause-save":
                self.dismiss()
                self.app.push_screen(SaveLoadScreen(mode="save"))
            case "btn-pause-load":
                self.dismiss()
                self.app.push_screen(SaveLoadScreen(mode="load"))
            case "btn-pause-title":
                self.dismiss()
                # 게임 화면을 모두 제거하고 타이틀로
                self.app.switch_screen(TitleScreen())
            case "btn-pause-continue":
                self.dismiss()


# ═══════════════════════════════════════════════════════════════
# 세이브 / 로드 모달
# ═══════════════════════════════════════════════════════════════

class SaveLoadScreen(ModalScreen):
    """세이브/로드 모달 다이얼로그."""

    CSS_PATH = "styles.tcss"

    def __init__(self, mode: str = "save", state_manager=None) -> None:
        """
        Args:
            mode: "save" 또는 "load"
            state_manager: 공유 StateManager 인스턴스 (None 이면 app.engine에서 조회)
        """
        super().__init__()
        self._mode = mode
        self._saves: list[dict] = []
        self._selected_idx: int = -1
        self._state_manager = state_manager

    def compose(self) -> ComposeResult:
        title = "게임 저장" if self._mode == "save" else "게임 불러오기"
        yield Container(
            Static(f"[bold]━━ {title} ━━[/bold]", id="saveload-title"),
            DataTable(id="save-table"),
            Container(
                Input(
                    placeholder="새 저장 이름 (저장 시)",
                    id="save-name-input",
                ),
                id="save-name-container",
            ) if self._mode == "save" else Static(""),
            Horizontal(
                Button("확인", id="btn-saveload-confirm", classes="saveload-btn"),
                Button("삭제", id="btn-saveload-delete", classes="saveload-btn"),
                Button("닫기", id="btn-saveload-close", classes="saveload-btn"),
                id="saveload-buttons",
            ),
            id="saveload-dialog",
        )

    def on_mount(self) -> None:
        """세이브 목록을 DataTable에 로드한다."""
        if self._state_manager is None:
            engine = getattr(self.app, "engine", None)
            if engine:
                self._state_manager = engine.state_manager
            else:
                from ..engine.state_manager import StateManager
                self._state_manager = StateManager()
        self._saves = self._state_manager.list_saves()

        table = self.query_one(DataTable)
        table.add_columns("이름", "캐릭터", "세계관", "저장 시간", "턴")
        for s in self._saves:
            table.add_row(
                s.get("name", ""),
                f"{s.get('character', '')} ({s.get('char_class', '')})",
                s.get("world", ""),
                s.get("timestamp", ""),
                str(s.get("turn_count", 0)),
            )

        if self._mode == "save":
            # 저장 이름 입력란에 기본값
            engine = getattr(self.app, "engine", None)
            if engine:
                char = engine.state_manager.game_state.character.name
                default_name = f"{char}의 모험"
                try:
                    self.query_one("#save-name-input", Input).value = default_name
                except Exception as exc:
                    logger.debug("save-name-input 기본값 설정 실패: {}", exc)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """테이블에서 행을 선택했을 때 인덱스를 저장한다."""
        self._selected_idx = event.cursor_row

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-saveload-confirm":
                self._handle_confirm()
            case "btn-saveload-delete":
                self._handle_delete()
            case "btn-saveload-close":
                self.dismiss()

    def _handle_confirm(self) -> None:
        """저장 또는 불러오기를 수행한다."""
        if self._mode == "save":
            try:
                name = self.query_one("#save-name-input", Input).value.strip()
            except Exception as exc:
                logger.debug("save-name-input 읽기 실패: {}", exc)
                name = ""
            if not name:
                name = "자동저장"
            self.dismiss()
            self.app.call_later(self._do_save, name)  # type: ignore[attr-defined]
        else:
            if self._selected_idx < 0 or self._selected_idx >= len(self._saves):
                self.app.notify("불러올 파일을 선택하세요.", severity="warning")
                return
            slot = self._saves[self._selected_idx].get("file", "")
            self.dismiss()
            self.app.call_later(self.app.load_game, slot)  # type: ignore[attr-defined]

    def _handle_delete(self) -> None:
        """선택된 세이브를 삭제한다."""
        if self._selected_idx < 0 or self._selected_idx >= len(self._saves):
            self.app.notify("삭제할 파일을 선택하세요.", severity="warning")
            return
        slot = self._saves[self._selected_idx].get("file", "")
        self._state_manager.delete_save(slot)
        self.app.notify(f"'{slot}' 세이브를 삭제했습니다.")
        self.dismiss()

    async def _do_save(self, slot_name: str) -> None:
        """실제 저장을 수행한다."""
        engine = getattr(self.app, "engine", None)
        if engine:
            try:
                path = await engine.save_game(slot_name)
                self.app.notify(f"저장 완료: {path}")
            except Exception as exc:
                self.app.notify(f"저장 실패: {exc}", severity="error")


# ═══════════════════════════════════════════════════════════════
# 게임 오버 화면
# ═══════════════════════════════════════════════════════════════

class GameOverScreen(Screen):
    """게임 오버 화면."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("r", "restart", "재시작"),
        ("n", "new_game", "새 게임"),
        ("q", "title", "타이틀"),
    ]

    def __init__(self, last_narrative: str = "") -> None:
        super().__init__()
        self._last_narrative = last_narrative

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                "[bold red]" + "█" * 9 + " GAME OVER " + "█" * 9 + "[/bold red]",
                id="gameover-title",
            ),
            ScrollableContainer(
                Static(self._last_narrative, id="gameover-text"),
            ),
            Horizontal(
                Button("[R] 재시작", id="btn-restart", classes="gameover-btn"),
                Button("[N] 새 게임", id="btn-new", classes="gameover-btn"),
                Button("[Q] 타이틀", id="btn-title", classes="gameover-btn"),
                id="gameover-buttons",
            ),
            id="gameover-container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-restart":
                self.action_restart()
            case "btn-new":
                self.action_new_game()
            case "btn-title":
                self.action_title()

    def action_restart(self) -> None:
        """마지막 세이브에서 재시작한다."""
        self.app.switch_screen(TitleScreen())
        self.app.push_screen(SaveLoadScreen(mode="load"))

    def action_new_game(self) -> None:
        """새 게임 설정 화면으로 이동한다."""
        self.app.switch_screen(SetupScreen())

    def action_title(self) -> None:
        """타이틀 화면으로 이동한다."""
        self.app.switch_screen(TitleScreen())
