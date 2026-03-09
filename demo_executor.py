import argparse
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def resolve_output_dir() -> Path:
    docker_output_dir = Path("/outputs")
    if (
        docker_output_dir.exists()
        and docker_output_dir.is_dir()
        and os.access(docker_output_dir, os.W_OK | os.X_OK)
    ):
        out_dir = docker_output_dir
    else:
        project_root = Path(__file__).resolve().parent.parent
        out_dir = project_root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


OUT_DIR = resolve_output_dir()


def get_scenario_actions(name):
    demo_query = os.getenv("DEMO_QUERY", "playwright browser automation")
    wiki_query = os.getenv("WIKI_QUERY", "Playwright")
    scenarios = {
        "todomvc": [
            {"type": "goto", "url": "https://demo.playwright.dev/todomvc/"},
            {"type": "wait_for_selector", "selector": ".new-todo"},
            {"type": "fill", "selector": ".new-todo", "text": "Plan FARA workflow"},
            {"type": "press", "selector": ".new-todo", "key": "Enter"},
            {"type": "fill", "selector": ".new-todo", "text": "Record end-to-end demo"},
            {"type": "press", "selector": ".new-todo", "key": "Enter"},
            {"type": "click", "selector": ".todo-list li:nth-child(1) .toggle"},
            {"type": "click", "selector": "a:has-text('Active')"},
            {"type": "wait_for_selector", "selector": ".todo-list li"},
            {"type": "click", "selector": "a:has-text('Completed')"},
            {"type": "wait_for_selector", "selector": ".todo-list li"},
            {"type": "sleep", "ms": 800},
        ],
        "wikipedia": [
            {"type": "goto", "url": "https://www.wikipedia.org/"},
            {"type": "wait_for_selector", "selector": "input#searchInput"},
            {"type": "fill", "selector": "input#searchInput", "text": wiki_query},
            {"type": "press", "selector": "input#searchInput", "key": "Enter"},
            {"type": "wait_for_selector", "selector": "#firstHeading"},
            {"type": "wait_for_url_contains", "value": "/wiki/"},
            {"type": "click", "selector": "#mw-content-text p a"},
            {"type": "sleep", "ms": 1000},
        ],
        "example": [
            {"type": "goto", "url": "https://example.com/"},
            {"type": "wait_for_selector", "selector": "h1"},
            {"type": "click", "selector": "a"},
            {"type": "goto", "url": "https://www.iana.org/domains/example"},
            {"type": "wait_for_selector", "selector": "h1"},
            {"type": "sleep", "ms": 1000},
        ],
        "duckduckgo_search": [
            {"type": "goto", "url": "https://duckduckgo.com/"},
            {"type": "wait_for_selector", "selector": "input[name='q']"},
            {"type": "fill", "selector": "input[name='q']", "text": demo_query},
            {"type": "press", "selector": "input[name='q']", "key": "Enter"},
            {"type": "wait_for_selector", "selector": "[data-testid='result'] h2 a"},
            {"type": "click", "selector": "[data-testid='result'] h2 a"},
            {"type": "sleep", "ms": 1000},
        ],
    }
    if name not in scenarios:
        raise ValueError(f"Unknown scenario: {name}")
    return scenarios[name]


def execute_action(page, action, state):
    action_type = action["type"]
    if action_type == "goto":
        page.goto(action["url"], wait_until="domcontentloaded", timeout=30000)
        state["url"] = page.url
    elif action_type == "wait_for_selector":
        page.wait_for_selector(action["selector"], timeout=action.get("timeout_ms", 15000))
    elif action_type == "fill":
        locator = page.locator(action["selector"]).first
        locator.wait_for(state="visible", timeout=action.get("timeout_ms", 10000))
        locator.fill(action["text"])
    elif action_type == "press":
        locator = page.locator(action["selector"]).first
        locator.wait_for(state="visible", timeout=action.get("timeout_ms", 10000))
        locator.press(action["key"])
    elif action_type == "click":
        locator = page.locator(action["selector"]).first
        locator.wait_for(state="visible", timeout=action.get("timeout_ms", 10000))
        locator.click(timeout=action.get("timeout_ms", 10000))
    elif action_type == "wait_for_url_contains":
        value = action["value"]
        page.wait_for_url(f"**{value}**", timeout=action.get("timeout_ms", 15000))
    elif action_type == "sleep":
        page.wait_for_timeout(action.get("ms", 1000))
    else:
        raise ValueError(f"Unsupported action type: {action_type}")


def execute_action_with_retry(page, action, state, max_attempts=2):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            execute_action(page, action, state)
            return
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                print(f"[INFO] Retrying action {action['type']} ({attempt}/{max_attempts})")
                page.wait_for_timeout(900)
    raise last_error


def run_demo(scenario_name=None):
    scenario = scenario_name or os.getenv("DEMO_SCENARIO", "todomvc")
    actions = get_scenario_actions(scenario)
    run_id = os.getenv("DEMO_RUN_ID", time.strftime("%Y%m%d_%H%M%S"))
    run_dir = OUT_DIR / scenario / run_id
    screenshot_dir = run_dir / "screenshots"
    trace_dir = run_dir / "traces"
    video_dir = run_dir / "videos"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Scenario: {scenario}")
    print(f"[INFO] Run output: {run_dir}")

    with sync_playwright() as p:
        slow_mo_ms = int(os.getenv("DEMO_SLOW_MO_MS", "0"))
        browser = p.chromium.launch(
            headless=os.getenv("DEMO_HEADLESS", "true").lower() != "false",
            slow_mo=slow_mo_ms,
        )
        context = browser.new_context(
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        state = {"scenario": scenario}

        for i, action in enumerate(actions, start=1):
            trace = {
                "scenario": scenario,
                "step": i,
                "action": action,
                "url_before": page.url,
                "status": "success",
            }
            print(f"[ACTION {i}] {action}")
            try:
                execute_action_with_retry(page, action, state, max_attempts=2)
            except Exception as exc:
                trace["status"] = "failed"
                trace["error"] = str(exc)
                print(f"[WARN] Step {i} failed: {exc}")

            screenshot_path = screenshot_dir / f"step_{i:02d}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            trace["url_after"] = page.url
            trace["title_after"] = page.title()
            trace_file = trace_dir / f"trace_{i:02d}.json"
            with open(trace_file, "w") as f:
                json.dump(trace, f, indent=2)
            time.sleep(0.5)

        hold_open_seconds = int(os.getenv("DEMO_HOLD_OPEN_SECONDS", "0"))
        if hold_open_seconds > 0:
            print(f"[INFO] Holding browser open for {hold_open_seconds}s")
            page.wait_for_timeout(hold_open_seconds * 1000)

        context.close()
        browser.close()

    webm_files = sorted(video_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if webm_files:
        latest = webm_files[-1]
        renamed = video_dir / f"{scenario}_{run_id}.webm"
        if latest != renamed:
            latest.rename(renamed)
        print(f"[INFO] Video: {renamed}")
    else:
        print("[WARN] No video file found")

    return str(run_dir)


def parse_args():
    parser = argparse.ArgumentParser(description="Playwright demo scenario executor")
    parser.add_argument(
        "--scenario",
        default=os.getenv("DEMO_SCENARIO", "todomvc"),
        help="Scenario name to execute",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List available scenarios and exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    available = ["todomvc", "wikipedia", "example", "duckduckgo_search"]
    if args.list_scenarios:
        print("\n".join(available))
    else:
        run_demo(args.scenario)
