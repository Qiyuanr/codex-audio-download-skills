#!/usr/bin/env python3
"""Run the shared downloader with the Bilibili platform guard."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path


PLATFORM = "Bilibili"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        skills_root = Path(__file__).resolve(strict=True).parents[2]
        core = (
            skills_root
            / "download-best-audio"
            / "scripts"
            / "download_audio.py"
        ).resolve(strict=True)
        if not core.is_file():
            raise OSError
    except (IndexError, OSError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "shared_skill_missing",
                    "message": "缺少共享 Skill：请同时安装 download-best-audio。",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2

    sys.argv = [str(core), *sys.argv[1:], "--expected-platform", PLATFORM]
    runpy.run_path(str(core), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
