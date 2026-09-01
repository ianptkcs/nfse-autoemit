"""Persistent browser context, timeouts, session management, helpers."""

from __future__ import annotations

import glob
import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Locator, Page

from nfse_config import NotaConfig

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile / artifact dirs
# ---------------------------------------------------------------------------

_DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "nfse-autoemit"
_DEFAULT_PROFILE_DIR = _DEFAULT_STATE_DIR / "chromium-profile"
_DEFAULT_ARTIFACT_DIR = _DEFAULT_STATE_DIR / "artifacts"
_CDP_PORT = 9222


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_brave_profile() -> Path | None:
    """Find the user's real Brave profile directory."""
    # Snap Brave (most common on Ubuntu)
    snap_dirs = sorted(glob.glob(str(Path.home() / "snap" / "brave" / "*")), reverse=True)
    for d in snap_dirs:
        profile = Path(d) / ".config" / "BraveSoftware" / "Brave-Browser"
        if profile.exists():
            return profile

    # Standard Brave
    standard = Path.home() / ".config" / "BraveSoftware" / "Brave-Browser"
    if standard.exists():
        return standard

    return None


# ---------------------------------------------------------------------------
# Brave launcher
# ---------------------------------------------------------------------------


def _find_brave() -> str | None:
    """Find the Brave browser executable."""
    import shutil

    for name in ["brave", "brave-browser", "brave-browser-stable"]:
        path = shutil.which(name)
        if path:
            return path

    # Check snap
    snap_path = Path("/snap/bin/brave")
    if snap_path.exists():
        return str(snap_path)

    return None


def is_brave_running() -> bool:
    """Check if Brave is running."""
    import subprocess

    try:
        result = subprocess.run(["pgrep", "-x", "brave"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def is_cdp_enabled(port: int = _CDP_PORT) -> bool:
    """Check if Brave is running with remote debugging on the given port."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def kill_brave() -> None:
    """Kill all Brave processes."""
    subprocess.run(["killall", "brave"], capture_output=True, timeout=5)
    time.sleep(2)


def launch_brave_with_cdp() -> bool:
    """Launch Brave with remote debugging using the user's real profile.

    Returns True if successfully launched, False otherwise.
    """
    brave_cmd = _find_brave()
    if not brave_cmd:
        log.error("Brave não encontrado no sistema")
        return False

    profile = _find_brave_profile()
    if not profile:
        log.error("Profile do Brave não encontrado")
        return False

    cmd = [
        brave_cmd,
        f"--remote-debugging-port={_CDP_PORT}",
        f"--user-data-dir={profile.parent}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    log.info("Iniciando Brave com CDP: %s", " ".join(cmd))
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for remote debugging
    for _ in range(20):
        time.sleep(0.5)
        if is_cdp_enabled():
            log.info("Brave pronto com CDP")
            return True

    log.error("Brave não respondeu na porta %d", _CDP_PORT)
    return False


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def is_session_expired(page: Page) -> bool:
    """Return True if the session is not authenticated.

    Checks if the page is on a login/SSO page instead of the actual NFS-e
    portal pages (which have /DPS/ in the URL).
    """
    url = page.url
    # Not authenticated if redirected to NFS-e login page
    if "/EmissorNacional/Login" in url:
        return True
    # Not authenticated if on gov.br SSO login page
    if "sso.acesso.gov.br" in url and "/login" in url:
        return True
    # Not authenticated if on any other login-related page
    if "/login" in url.lower() and "/EmissorNacional/" not in url:
        return True
    return False


def check_session(page: Page) -> None:
    """Raise if session is expired — call after every navigation/reload."""
    if is_session_expired(page):
        raise RuntimeError(
            "Sessão expirou — redirecionado para /Login. "
            "Execute `uv run bin/nfse_emit.py login` para re-autenticar."
        )


# ---------------------------------------------------------------------------
# Browser launch
# ---------------------------------------------------------------------------


def launch_browser(cfg: NotaConfig) -> BrowserContext:
    """Launch a browser context.

    If ``cfg.cdp_url`` is set, connects to an existing browser via CDP
    (Chrome DevTools Protocol). This bypasses gov.br's bot detection because
    the browser is the user's real browser, not Playwright's bundled one.

    Otherwise, launches a persistent Firefox context (Chromium triggers
    gov.br's hcaptcha).

    Returns a ``BrowserContext`` — the caller is responsible for closing it.
    """
    pw = sync_playwright().start()

    # CDP mode: connect to user's real browser
    if cfg.cdp_url:
        log.info("Conectando ao browser via CDP: %s", cfg.cdp_url)
        browser = pw.chromium.connect_over_cdp(cfg.cdp_url)
        # Get the default context (or create one)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="pt-BR",
            )
        context._pw_instance = pw  # type: ignore[attr-defined]
        context._cdp_browser = browser  # type: ignore[attr-defined]
        if not context.pages:
            context.new_page()
        return context

    # Standalone mode: launch persistent Firefox
    profile = Path(cfg.profile_dir) if cfg.profile_dir else _DEFAULT_PROFILE_DIR
    _ensure_dir(profile)

    context = pw.firefox.launch_persistent_context(
        user_data_dir=str(profile),
        headless=cfg.headless,
        slow_mo=cfg.slow_mo_ms,
        viewport={"width": 1280, "height": 900},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )

    # Store playwright instance on context for cleanup
    context._pw_instance = pw  # type: ignore[attr-defined]

    # Ensure at least one page exists
    if not context.pages:
        context.new_page()

    return context


def close_browser(context: BrowserContext) -> None:
    """Close context and stop playwright."""
    pw = getattr(context, "_pw_instance", None)
    browser = getattr(context, "_cdp_browser", None)

    if browser is not None:
        # CDP mode: disconnect (don't close the user's browser)
        browser.close()
    else:
        # Standalone mode: close the context
        context.close()

    if pw is not None:
        pw.stop()


# ---------------------------------------------------------------------------
# Helpers — select_searchable
# ---------------------------------------------------------------------------


def select_searchable(
    scope: Locator | Page,
    field: Locator,
    query: str,
    option_label: str,
    *,
    timeout_ms: int = 10_000,
) -> None:
    """Interact with a searchable dropdown (click, type, select option).

    Used for Município and Código de Tributação selects that require
    typing to filter, then clicking an option from the dropdown.
    """
    field.click()
    time.sleep(0.3)  # wait for dropdown to open

    # Clear any existing value
    field.press("Control+a")
    field.press("Backspace")

    # Type to filter — press_sequentially with delay for Angular reactive inputs
    field.press_sequentially(query, delay=50)

    # Wait for the option to appear
    option = scope.locator(f"text='{option_label}'").first
    option.wait_for(state="visible", timeout=timeout_ms)
    option.click()

    # Read back to confirm selection
    time.sleep(0.2)
    actual = field.input_value()
    if option_label.split(" - ")[0].strip() not in actual and option_label not in actual:
        log.warning("select_searchable: valor lido %r não confere com %r", actual, option_label)


# ---------------------------------------------------------------------------
# Helpers — fill_masked
# ---------------------------------------------------------------------------


def fill_masked(locator: Locator, expected: str, *, timeout_ms: int = 5_000) -> None:
    """Fill a masked input field (date, currency) reliably.

    The portal's masked fields sometimes ignore plain ``fill()``. Strategy:
    fill -> read back -> if divergent, clear + type digit by digit -> re-read.
    """
    locator.fill(expected)
    time.sleep(0.2)

    actual = locator.input_value()
    if actual.strip() == expected.strip():
        return

    # Retry: clear and type character by character
    locator.click()
    locator.press("Control+a")
    locator.press("Backspace")
    locator.press_sequentially(expected, delay=30)
    time.sleep(0.3)

    actual = locator.input_value()
    if actual.strip() != expected.strip():
        raise RuntimeError(f"fill_masked: campo não aceitou valor {expected!r} (leu {actual!r})")


# ---------------------------------------------------------------------------
# Helpers — ensure_radio
# ---------------------------------------------------------------------------


def ensure_radio(scope: Locator | Page, group_label: str, option: str) -> None:
    """Select a radio option and assert it's checked.

    Even for defaults, we confirm — catches portal drift.
    """
    radio = scope.get_by_label(option, exact=True).first
    if not radio.is_checked():
        radio.click()
        time.sleep(0.1)
    assert radio.is_checked(), f"Radio {group_label!r} / {option!r} não ficou marcado"


# ---------------------------------------------------------------------------
# Helpers — retry_step
# ---------------------------------------------------------------------------


def retry_step(
    page: Page,
    fn: Any,
    *,
    attempts: int = 3,
    timeout_ms: int = 20_000,
) -> None:
    """Retry an entire wizard step (not individual fields).

    On failure: detect error modal, close it, reload, check session, re-execute fn.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            fn(page)
            return
        except (PlaywrightTimeout, RuntimeError) as exc:
            last_exc = exc
            log.warning("retry_step: tentativa %d/%d falhou: %s", attempt, attempts, exc)

            # Try to close error modal if present
            try:
                modal_text = is_error_modal(page)
                if modal_text:
                    log.warning("retry_step: modal de erro detectado: %s", modal_text)
                    close_btn = page.locator("button:has-text('Fechar'), button:has-text('OK')")
                    if close_btn.count() > 0:
                        close_btn.first.click()
                        time.sleep(0.5)
            except Exception:
                pass

            # Reload and check session
            page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
            check_session(page)
            time.sleep(1)

    raise RuntimeError(f"retry_step: {attempts} tentativas falharam") from last_exc


# ---------------------------------------------------------------------------
# Helpers — is_error_modal
# ---------------------------------------------------------------------------


def is_error_modal(page: Page) -> str | None:
    """Detect the portal's error modal (\"Não foi possível...\").

    Returns the modal text if found, None otherwise.
    """
    try:
        dialog = page.locator("[role='dialog'], .modal, .p-dialog")
        if dialog.count() > 0 and dialog.first.is_visible():
            text = dialog.first.inner_text()
            if "Não foi possível" in text or "Mensagem do Sistema" in text:
                return text
    except Exception:
        pass
    return None
