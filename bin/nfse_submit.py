"""The ONLY module that clicks 'Emitir NFS-e'.

Small, easy to audit via grep. All submission safety lives here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nfse_selectors import EmitirSelectors
from nfse_wizard import ReviewSummary

if TYPE_CHECKING:
    from playwright.sync_api import Page

log = logging.getLogger(__name__)


def submit(page: Page, summary: ReviewSummary, *, confirmed: bool) -> str:
    """Click the 'Emitir NFS-e' button.

    Raises ``RuntimeError`` if ``confirmed`` is not ``True`` — no default,
    no shortcut.
    """
    if confirmed is not True:
        raise RuntimeError(
            "submit() requer confirmed=True explicitamente. "
            "Chamar com submit(page, summary, confirmed=True)."
        )

    log.info("Submetendo NFS-e (confirmado pelo usuário)")

    btn = EmitirSelectors.btn_emitir(page)
    btn.click()

    # Wait for success indicator
    page.wait_for_timeout(3_000)

    # Try to capture NFS-e number from success message
    success_text = ""
    try:
        success_dialog = page.locator("[role='dialog'], .modal, .p-dialog")
        if success_dialog.count() > 0 and success_dialog.first.is_visible():
            success_text = success_dialog.first.inner_text()
    except Exception:
        pass

    # Also check for NFS-e number in page content
    import re

    try:
        content = page.content()
        if not isinstance(content, str):
            content = ""
    except Exception:
        content = ""
    nfse_match = re.search(r"NFS-e\s*(?:nº|número|#)\s*(\d+)", content)
    nfse_number = nfse_match.group(1) if nfse_match else ""

    if nfse_number:
        log.info("NFS-e emitida: nº %s", nfse_number)
    elif success_text:
        log.info("Resposta do portal: %s", success_text[:200])
    else:
        log.warning("Não foi possível capturar número da NFS-e")

    return nfse_number or success_text
