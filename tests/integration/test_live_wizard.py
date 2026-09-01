"""Integration test: exercises the real portal (requires NFSE_LIVE=1).

This test is excluded from CI by default (addopts: -m 'not integration').
Run manually: NFSE_LIVE=1 uv run pytest tests/integration/test_live_wizard.py -v
"""

from __future__ import annotations

import os

import pytest

from nfse_config import NotaConfig, load_config

pytestmark = pytest.mark.integration


@pytest.fixture
def live_cfg() -> NotaConfig:
    """Load config from environment, requiring NFSE_LIVE=1."""
    if os.environ.get("NFSE_LIVE") != "1":
        pytest.skip("NFSE_LIVE=1 not set")
    return load_config(os.environ)


@pytest.fixture
def browser_context(live_cfg: NotaConfig):
    """Launch browser for integration test."""
    from nfse_browser import launch_browser

    ctx = launch_browser(live_cfg)
    yield ctx
    ctx.close()


class TestLiveWizard:
    def test_full_wizard_to_review(self, live_cfg: NotaConfig, browser_context) -> None:
        """Navigate through the wizard and stop at review (never submit)."""
        from nfse_browser import retry_step
        from nfse_wizard import fill_pessoas, fill_servico, fill_tributacao, read_review

        page = browser_context.new_page()
        page.goto(f"{live_cfg.base_url}/EmissorNacional/DPS/Pessoas", timeout=live_cfg.timeout_ms)

        if page.url.endswith("/Login"):
            pytest.skip("Session expired — run `uv run bin/nfse_emit.py login` first")

        retry_step(page, lambda p: fill_pessoas(p, live_cfg))
        retry_step(page, lambda p: fill_servico(p, live_cfg))
        retry_step(page, lambda p: fill_tributacao(p, live_cfg))

        summary = read_review(page)
        assert summary.tomador_cnpj or summary.valor, "Review page should have data"
