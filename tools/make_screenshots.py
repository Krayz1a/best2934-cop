"""Render the README screenshots from real program output.

Every image here is produced by running the actual code and capturing what it
actually printed -- not by mocking up something that looks like it. The
terminal frames are drawn as monospace text on a dark canvas so they read like
the terminal they came from.

    uv run python tools/make_screenshots.py

The Tkinter belief-map screenshot is not produced here: Tk ships as the
``python3-tk`` system package rather than through uv, so on a machine without it
this script says so and skips that one image rather than faking it.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2pchase.sdk.sdk import P2PChaseSDK  # noqa: E402
from p2pchase.shared.config import load_config  # noqa: E402
from p2pchase.ui.live_view import run_text_view  # noqa: E402

ASSETS = ROOT / "assets"
BACKGROUND = "#0d1117"
FOREGROUND = "#d6deeb"


def render_text(text: str, name: str, title: str, char_width: float = 0.098) -> None:
    """Draw captured terminal output as an image, sized to the text it holds."""
    lines = text.rstrip("\n").split("\n")
    width = max(len(line) for line in lines) * char_width + 0.6
    height = len(lines) * 0.19 + 0.75

    fig = plt.figure(figsize=(width, height), facecolor=BACKGROUND)
    fig.text(0.02, 1 - 0.28 / height, title, family="monospace", fontsize=9,
             color="#7d8590", va="top")
    fig.text(0.02, 1 - 0.62 / height, "\n".join(lines), family="monospace",
             fontsize=9, color=FOREGROUND, va="top", linespacing=1.35)

    ASSETS.mkdir(parents=True, exist_ok=True)
    path = ASSETS / name
    fig.savefig(path, dpi=150, facecolor=BACKGROUND, bbox_inches="tight")
    plt.close(fig)
    print(f"  {path.relative_to(ROOT)}")


def shot_live_view_text(sdk: P2PChaseSDK) -> None:
    """The terminal belief view: local truth only, no opponent position."""
    frame = run_text_view(sdk, seed=7, delay=0.0, quiet=True, opponent="rival999")
    render_text(frame, "live_view_text.png",
                "$ uv run p2pchase gui --role police --text")


def shot_replay(sdk: P2PChaseSDK, log: Path) -> None:
    """A verified replay, and the same log after one byte is altered."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print(sdk.replay_text(log, limit=12))
    render_text(buffer.getvalue(), "replay_verified_ok.png",
                f"$ uv run p2pchase verify --log {log.name}")

    payload = json.loads(log.read_text(encoding="utf-8"))
    payload["records"][3]["payload"]["move"] = "STAY"
    tampered = log.with_name("tampered_" + log.name)
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print(sdk.replay_text(tampered, limit=12))
    render_text(buffer.getvalue(), "replay_tampered.png",
                f"$ uv run p2pchase verify --log {tampered.name}   # one byte changed")
    tampered.unlink()


def main() -> int:
    print("rendering screenshots into assets/ ...")
    sdk = P2PChaseSDK(load_config(ROOT / "config" / "police", "police"),
                      output_dir=ROOT / "artifacts")
    shot_live_view_text(sdk)

    series = sdk.run_series("rival999", sub_games=1, seed=11)
    log = next(p for p in series.paths if p.name.startswith("log_"))
    shot_replay(sdk, log)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("\n  assets/live_view_belief_map.png NOT generated: Tkinter is missing.\n"
              "  It ships as the python3-tk system package, not through uv:\n"
              "      sudo apt install python3-tk\n"
              "  Then run:  uv run p2pchase gui --role police\n"
              "  and capture the window. This script will not fake that image.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
