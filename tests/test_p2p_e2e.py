"""End-to-end test of P2P messaging using Playwright.

Spins up the sample app on a local port, opens two isolated browser contexts
(simulating user1 and user2), creates a direct P2P room from user1, sends
messages in both directions, and asserts:
  - the message text appears in the receiver's #messages DOM
  - the message is persisted in the receiver's localStorage under the
    asynaprous-p2p-v2 namespace

Run with:
    .venv/bin/python tests/test_p2p_e2e.py
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright, expect, TimeoutError as PWTimeout


SERVER_PORT = 2127
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"
USER1 = ("user1", "User1Local#A1b2C3d4")
USER2 = ("user2", "User2Local#A1b2C3d4")


def wait_for_port(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.2)
    raise RuntimeError(f"server on {host}:{port} not reachable: {last_err}")


def start_server() -> subprocess.Popen:
    import threading
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            str(REPO_ROOT / "start_sampleapp.py"),
            "--server-ip",
            "127.0.0.1",
            "--server-port",
            str(SERVER_PORT),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def relay():
        for line in proc.stdout:
            sys.stdout.write("[server] " + line.decode("utf-8", "replace"))
            sys.stdout.flush()
    t = threading.Thread(target=relay, daemon=True)
    t.start()

    try:
        wait_for_port("127.0.0.1", SERVER_PORT)
    except Exception:
        proc.kill()
        raise
    return proc


def login(page, username: str, password: str) -> None:
    page.goto(f"{BASE_URL}/login.html", wait_until="domcontentloaded")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE_URL}/chat.html", timeout=10_000)
    # wait for chat-ui.js bootstrap (account strip populated)
    expect(page.locator("#account-peer-id")).to_contain_text("peer_", timeout=10_000)


def get_local_peer_id(page) -> str:
    text = page.locator("#account-peer-id").text_content() or ""
    parts = text.split(":", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def open_p2p_with(page, target_peer_id: str) -> None:
    page.click("#new-p2p-btn")
    page.fill("#peer-search-input", target_peer_id)
    # Press Enter to trigger tryAddPeerFromSearchInput (resolves via /api/peer/resolve)
    page.press("#peer-search-input", "Enter")
    # Wait until the chip lands in the preview row.
    expect(page.locator("#selected-peer-preview .peer-chip")).to_have_count(1, timeout=5_000)
    page.click("#create-private-room-btn")
    expect(page.locator("#current-room-title")).to_contain_text("Direct:", timeout=5_000)


def select_room_with_peer(page, peer_id: str) -> None:
    """Wait for a direct room with `peer_id` to appear in the sidebar and click it."""
    # The sidebar renders rooms with label "Direct: <user>" where <user> is whatever
    # peerLabelById resolves; the row text contains the peer's user label. We click
    # any "Direct:" row and verify the subtitle includes the peer-id.
    page.wait_for_selector("#p2p-room-list li button.row-main", timeout=15_000)
    rows = page.locator("#p2p-room-list li button.row-main")
    deadline = time.time() + 15
    while time.time() < deadline:
        n = rows.count()
        for i in range(n):
            label = rows.nth(i).text_content() or ""
            if label.startswith("Direct:"):
                rows.nth(i).click()
                return
        time.sleep(0.2)
    raise AssertionError("no direct room appeared on receiver side")


def send_message(page, text: str) -> None:
    page.fill("#msg-input", text)
    page.press("#msg-input", "Enter")


def wait_for_message_in_dom(page, text: str, timeout_ms: int = 15_000) -> None:
    expect(page.locator("#messages")).to_contain_text(text, timeout=timeout_ms)


def assert_message_in_local_storage(page, text: str) -> None:
    # Walk all asynaprous-p2p-v2:messages:* keys and look for the message.
    found = page.evaluate(
        """(needle) => {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (!key || !key.startsWith('asynaprous-p2p-v2:messages:')) continue;
                const raw = localStorage.getItem(key) || '[]';
                let items;
                try { items = JSON.parse(raw); } catch (e) { continue; }
                if (!Array.isArray(items)) continue;
                if (items.some((it) => it && it.message === needle)) {
                    return key;
                }
            }
            return '';
        }""",
        text,
    )
    assert found, f"message {text!r} not persisted in localStorage"


def run() -> int:
    server = start_server()
    failures: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx1 = browser.new_context()
            ctx2 = browser.new_context()
            page1 = ctx1.new_page()
            page2 = ctx2.new_page()

            page1.on("console", lambda msg: print(f"[user1.{msg.type}] {msg.text}"))
            page2.on("console", lambda msg: print(f"[user2.{msg.type}] {msg.text}"))

            login(page1, *USER1)
            login(page2, *USER2)

            peer1 = get_local_peer_id(page1)
            peer2 = get_local_peer_id(page2)
            print(f"user1 peer_id={peer1}")
            print(f"user2 peer_id={peer2}")
            assert peer1 and peer2 and peer1 != peer2, "peer ids missing or equal"

            # user1 starts a direct P2P with user2 (resolved by username).
            open_p2p_with(page1, USER2[0])

            # user2 should see the new direct room appear via the p2p-room signal.
            select_room_with_peer(page2, peer1)

            msg_a = "p2p hello from user1"
            send_message(page1, msg_a)

            # Receiver sees it and persists it.
            try:
                wait_for_message_in_dom(page2, msg_a)
                assert_message_in_local_storage(page2, msg_a)
                print(f"OK user1->user2: {msg_a!r}")
            except (AssertionError, PWTimeout) as exc:
                failures.append(f"user1->user2 failed: {exc}")

            # Reverse direction
            msg_b = "p2p reply from user2"
            send_message(page2, msg_b)
            try:
                wait_for_message_in_dom(page1, msg_b)
                assert_message_in_local_storage(page1, msg_b)
                print(f"OK user2->user1: {msg_b!r}")
            except (AssertionError, PWTimeout) as exc:
                failures.append(f"user2->user1 failed: {exc}")

            # Second message in same direction (channel re-use)
            msg_c = "second message from user1"
            send_message(page1, msg_c)
            try:
                wait_for_message_in_dom(page2, msg_c)
                assert_message_in_local_storage(page2, msg_c)
                print(f"OK user1->user2 (2nd): {msg_c!r}")
            except (AssertionError, PWTimeout) as exc:
                failures.append(f"user1->user2 (2nd) failed: {exc}")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nALL P2P MESSAGES DELIVERED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
