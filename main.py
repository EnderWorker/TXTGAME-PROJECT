"""
Text RPG Engine 메인 엔트리포인트.

Playwright Chromium 설치 여부를 확인하고,
설정을 로드한 뒤 TextRPGApp을 실행한다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def check_first_run() -> None:
    """Playwright Chromium 설치 여부를 확인한다.

    미설치 시 자동으로 다운로드한다 (약 150MB, 최초 1회).
    """
    # Playwright 설치 확인
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("playwright 패키지가 설치되지 않았습니다.")
        print("pip install -r requirements.txt 를 실행해주세요.")
        sys.exit(1)

    # Chromium 설치 확인 (playwright install chromium)
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: F401
        import subprocess as sp
        result = sp.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "chromium" in result.stdout.lower() and "already installed" not in result.stdout.lower():
            raise RuntimeError("Chromium not installed")
    except Exception:
        print("필요한 구성요소를 설치합니다 (약 150MB, 최초 1회)...")
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Chromium 설치 실패: {e}")
            print("수동으로 'playwright install chromium' 을 실행해주세요.")
            sys.exit(1)


def load_config() -> dict:
    """config/settings.toml을 로드한다.

    파일이 없으면 기본값 dict를 반환한다.

    Returns:
        설정 dict
    """
    config_path = Path("config/settings.toml")
    if config_path.exists():
        try:
            import toml
            return toml.load(config_path)
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")

    # 기본값
    return {
        "genspark": {
            "base_url": "https://chat.genspark.ai",
            "default_model": "Claude Sonnet",
            "headless": True,
            "input_delay_min": 0.03,
            "input_delay_max": 0.08,
            "response_timeout": 120,
            "response_stable_duration": 3,
        },
        "session": {
            "cookie_file": "saves/genspark_session.json",
            "auto_save": True,
        },
        "game": {
            "max_exchanges_before_compaction": 25,
        },
        "logging": {
            "level": "DEBUG",
            "file": "logs/app.log",
        },
    }


def ensure_directories() -> None:
    """필요한 디렉터리를 생성한다."""
    for d in ("saves", "logs", "config/worlds"):
        Path(d).mkdir(parents=True, exist_ok=True)


def main() -> None:
    """메인 엔트리포인트."""
    ensure_directories()
    check_first_run()

    config = load_config()

    from src.ui.tui_app import TextRPGApp
    app = TextRPGApp(config=config)
    app.run()


if __name__ == "__main__":
    main()
