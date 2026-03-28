"""
빌드 스크립트.

실행:
    python build.py [--mode full|light]

    --mode full  : Chromium 바이너리 포함 (~300MB)
    --mode light : Chromium 미포함, 첫 실행 시 자동 다운로드 (~30MB)

결과물: dist/TextRPG/
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def find_chromium_path() -> Path | None:
    """Playwright가 설치한 Chromium 실행 파일 경로를 찾는다.

    Returns:
        Chromium 실행 파일이 있는 디렉터리, 없으면 None
    """
    try:
        import subprocess as sp
        result = sp.run(
            [sys.executable, "-m", "playwright", "install", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        # Playwright 캐시 디렉터리 탐색
        home = Path.home()
        candidate_dirs = [
            home / "AppData" / "Local" / "ms-playwright",           # Windows
            home / ".cache" / "ms-playwright",                       # Linux
            home / "Library" / "Caches" / "ms-playwright",           # macOS
        ]
        for d in candidate_dirs:
            if d.exists():
                chromium_dirs = list(d.glob("chromium-*"))
                if chromium_dirs:
                    latest = sorted(chromium_dirs)[-1]
                    return latest
    except Exception:
        pass
    return None


def build(mode: str = "light") -> None:
    """PyInstaller로 .exe를 빌드한다.

    Args:
        mode: "full" (Chromium 포함) 또는 "light" (Chromium 미포함)
    """
    print(f"=== TextRPG 빌드 시작 (mode={mode}) ===")

    dist_dir = Path("dist/TextRPG")
    if dist_dir.exists():
        print("이전 빌드 제거 중...")
        shutil.rmtree(dist_dir)

    # PyInstaller 인수
    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name", "TextRPG",
        "--onedir",                  # 단일 디렉터리 (onefile보다 빠른 시작)
        "--windowed",                # 콘솔 창 숨김 (GUI 앱)
        "--noconfirm",               # 기존 빌드 덮어쓰기
        # 필수 숨겨진 import
        "--hidden-import", "playwright",
        "--hidden-import", "playwright.async_api",
        "--hidden-import", "textual",
        "--hidden-import", "loguru",
        "--hidden-import", "toml",
        # 데이터 파일
        "--add-data", "config;config",
        "--add-data", f"src/ui/styles.tcss;src/ui",
        "main.py",
    ]

    # full 모드: Chromium 바이너리 포함
    if mode == "full":
        chromium_dir = find_chromium_path()
        if chromium_dir:
            print(f"Chromium 경로 발견: {chromium_dir}")
            pyinstaller_args += ["--add-data", f"{chromium_dir};ms-playwright/{chromium_dir.name}"]
            # 환경 변수로 Playwright에 경로 알림
            pyinstaller_args += ["--runtime-hook", "_playwright_hook.py"]
            _write_playwright_hook()
        else:
            print("경고: Chromium 경로를 찾지 못했습니다. light 모드로 빌드합니다.")

    # 빌드 실행
    print("PyInstaller 실행 중...")
    result = subprocess.run(pyinstaller_args, check=False)

    if result.returncode != 0:
        print("빌드 실패!")
        sys.exit(1)

    # 출력 디렉터리 정리
    _finalize_build(mode)

    print(f"\n=== 빌드 완료 ===")
    print(f"결과물: {dist_dir.resolve()}")
    print(f"실행: dist/TextRPG/TextRPG.exe")


def _write_playwright_hook() -> None:
    """PyInstaller 런타임 훅 파일을 생성한다.

    full 모드에서 번들된 Chromium 경로를 Playwright에 알린다.
    """
    hook_content = """
import os
import sys
from pathlib import Path

# 번들된 Playwright Chromium 경로 설정
_base = Path(sys._MEIPASS)
_playwright_dir = _base / "ms-playwright"
if _playwright_dir.exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_playwright_dir)
"""
    Path("_playwright_hook.py").write_text(hook_content, encoding="utf-8")
    print("Playwright 런타임 훅 생성 완료")


def _finalize_build(mode: str) -> None:
    """빌드 결과물을 정리하고 필요한 디렉터리를 생성한다."""
    dist_dir = Path("dist/TextRPG")

    if not dist_dir.exists():
        print("빌드 출력 디렉터리를 찾을 수 없습니다.")
        return

    # config 복사 (PyInstaller가 이미 처리하지만 확인 차 재복사)
    config_dst = dist_dir / "config"
    if not config_dst.exists() and Path("config").exists():
        shutil.copytree("config", config_dst)
        print("config/ 복사 완료")

    # saves, logs 디렉터리 생성
    for d in ("saves", "logs"):
        (dist_dir / d).mkdir(exist_ok=True)
    print("saves/, logs/ 디렉터리 생성 완료")

    # README 복사
    if Path("README.md").exists():
        shutil.copy("README.md", dist_dir / "README.md")

    # 임시 빌드 파일 정리
    for temp in (Path("build"), Path("TextRPG.spec"), Path("_playwright_hook.py")):
        if temp.is_dir():
            shutil.rmtree(temp, ignore_errors=True)
        elif temp.is_file():
            temp.unlink(missing_ok=True)

    print(f"빌드 모드: {mode}")
    if mode == "light":
        print("참고: light 모드로 빌드되었습니다.")
        print("      첫 실행 시 Chromium이 자동으로 다운로드됩니다 (~150MB).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TextRPG 빌드 스크립트")
    parser.add_argument(
        "--mode",
        choices=["full", "light"],
        default="light",
        help="full: Chromium 포함 (~300MB), light: 첫 실행 시 자동 다운로드 (~30MB)",
    )
    args = parser.parse_args()
    build(args.mode)
