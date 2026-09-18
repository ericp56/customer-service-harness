"""Browser journeys for the transient public Echo Web Chat page."""

from __future__ import annotations

import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import expect

from src import app


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def browser_runtime_available(browser) -> None:
    """Use pytest-playwright's browser fixture; it skips only if runtime setup is unavailable."""
    assert browser.is_connected()


@pytest.fixture(scope="session")
def echo_url(browser_runtime_available: None) -> str:
    server = uvicorn.Server(
        uvicorn.Config(
            app.create_server(),
            host="127.0.0.1",
            port=7860,
            access_log=False,
            log_level="critical",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = "http://127.0.0.1:7860"
    for _ in range(50):
        try:
            with urlopen(f"{url}/healthz", timeout=0.2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("Echo application did not become ready.")

    yield url

    server.should_exit = True
    thread.join(timeout=5)


def submit(page, text: str) -> None:
    page.locator("#echo-message textarea").fill(text)
    page.locator("#echo-send").click()


def test_normal_unicode_and_line_break_echo(page, echo_url: str) -> None:
    page.goto(echo_url)
    text = "Hello\n世界 <tag>"

    submit(page, text)

    conversation = page.locator("#echo-conversation")
    expect(conversation).to_contain_text("Hello")
    expect(conversation).to_contain_text("世界")
    expect(conversation).to_contain_text("<tag>")
    assert conversation.locator("script").count() == 0
    assert page.context.cookies() == []
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []


def test_accessible_validation_and_recovery(page, echo_url: str) -> None:
    page.goto(echo_url)

    submit(page, " \t")

    status = page.locator("#echo-status [role='alert']")
    expect(status).to_contain_text("non-whitespace")
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")


def test_keyboard_retry_recovers_a_declared_operational_failure(page, echo_url: str, monkeypatch) -> None:
    page.goto(echo_url)

    def fail(_: str) -> str:
        raise app.EchoOperationalError()

    monkeypatch.setattr(app, "generate_echo", fail)
    submit(page, "retry this")
    expect(page.locator("#echo-status [role='alert']")).to_contain_text("Retry is available")
    retry = page.locator("#echo-retry")
    expect(retry).to_be_visible()

    monkeypatch.setattr(app, "generate_echo", lambda text: text)
    retry.focus()
    retry.press("Enter")
    expect(page.locator("#echo-conversation [role='log']")).to_contain_text("retry this")


def test_fifty_pairs_require_new_conversation(page, echo_url: str) -> None:
    page.goto(echo_url)
    for number in range(50):
        submit(page, str(number))
        expect(page.locator("#echo-message textarea")).to_have_value("")

    expect(page.locator("#echo-new-conversation")).to_be_visible()
    page.locator("#echo-new-conversation").click()
    expect(page.locator("#echo-conversation [role='log']")).to_have_text("")
