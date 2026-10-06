"""Exercise the recording flow in a real 16:9 browser and leave no runtime behind.

Run with ``uv run scripts/browser-check.py``. This intentionally owns the local
runtime lifecycle so browser proof cannot be mistaken for a static-page check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Error, Page, sync_playwright


ROOT = Path(__file__).parents[1]
URL = "http://127.0.0.1:19440"
VIEWPORT = {"width": 1920, "height": 1080}


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


def recording_surface_is_usable(page: Page) -> None:
    report = page.evaluate(
        """() => {
          const critical = ["#page-title", "#proof-value", "#result", "#primary"];
          const visible = critical.map((selector) => {
            const element = document.querySelector(selector);
            const box = element?.getBoundingClientRect();
            const style = element ? getComputedStyle(element) : null;
            return {
              selector,
              text: element?.innerText?.trim() || "",
              visible: Boolean(element && box && style && style.visibility !== "hidden" &&
                style.display !== "none" && box.width > 0 && box.height > 0 &&
                box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight),
            };
          });
          return { scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth, visible };
        }"""
    )
    if report["scrollWidth"] > report["viewportWidth"]:
        raise AssertionError(f"16:9 page has horizontal overflow: {report}")
    hidden = [item for item in report["visible"] if not item["visible"] or not item["text"]]
    if hidden:
        raise AssertionError(f"critical recording text is not visible: {hidden}")


def assert_clean_page(errors: list[str]) -> None:
    if errors:
        raise AssertionError("browser errors:\n" + "\n".join(errors))


def run_flow(page: Page, errors: list[str]) -> None:
    # The proof page keeps an EventSource open, so network-idle is never a valid
    # browser-ready signal. The visible runtime label is the readiness proof.
    page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
    page.locator("#runtime-label").wait_for(state="visible")
    page.locator("#local-action").click()
    page.wait_for_function(
        """() => document.querySelector("#proof-value")?.textContent
          ?.includes("COMPRESSOR_OVERHEAT arrived, 1 / 1") &&
          document.querySelector("#result")?.textContent?.includes("Observed receiver traffic fell") &&
          document.querySelector("#ack strong")?.textContent?.startsWith("ACK ")""",
        timeout=45_000,
    )
    recording_surface_is_usable(page)
    assert_clean_page(errors)


def main() -> int:
    started = True
    outcome = 0
    try:
        command("./scripts/democtl.sh", "start", "local", "baseline")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport=VIEWPORT)
            page = context.new_page()
            errors: list[str] = []
            page.on(
                "console",
                lambda message: errors.append(f"console.{message.type}: {message.text}")
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
            try:
                run_flow(page, errors)
            finally:
                context.close()
                browser.close()
        print("browser acceptance passed: receiver acknowledged protected filtered incident")
    except (AssertionError, Error, subprocess.CalledProcessError) as error:
        print(f"browser acceptance failed: {error}", file=sys.stderr)
        outcome = 1
    finally:
        if started:
            stop = command("./scripts/democtl.sh", "stop", check=False)
            audit = command("./scripts/teardown-audit.sh", check=False)
            if stop.returncode or audit.returncode:
                print("browser acceptance cleanup failed", file=sys.stderr)
                outcome = 1
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
