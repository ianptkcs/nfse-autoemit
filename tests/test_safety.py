"""Tests for safety mechanisms: submit gate, preview never submits, non-TTY abort."""

from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from nfse_submit import submit
from nfse_wizard import ReviewSummary


def _fake_summary() -> ReviewSummary:
    return ReviewSummary(
        tomador_cnpj="11.222.333/0001-81",
        tomador_nome="Empresa Teste",
        municipio="Belo Horizonte/MG",
        descricao_servico="Datilografia",
        valor="1.500,00",
        competencia="01/09/2026",
    )


class TestSubmitSafety:
    def test_submit_requires_confirmed_true(self) -> None:
        page = MagicMock()
        summary = _fake_summary()

        with pytest.raises(RuntimeError, match="confirmed=True"):
            submit(page, summary, confirmed=False)

    def test_submit_requires_confirmed_not_none(self) -> None:
        page = MagicMock()
        summary = _fake_summary()

        with pytest.raises(RuntimeError, match="confirmed=True"):
            submit(page, summary, confirmed=None)  # type: ignore[arg-type]

    def test_submit_works_with_confirmed_true(self) -> None:
        page = MagicMock()
        summary = _fake_summary()

        # Should not raise
        submit(page, summary, confirmed=True)
        # Verify the button was clicked
        page.get_by_role.assert_called()


class TestPreviewSafety:
    def test_preview_never_calls_submit(self) -> None:
        """Preview mode should never call submit() — verified by code structure."""
        # cmd_preview doesn't import or call submit — this is a structural test
        import inspect

        from nfse_emit import cmd_preview

        source = inspect.getsource(cmd_preview)
        assert "submit(" not in source, "cmd_preview must not call submit()"


class TestEmitNonTTY:
    def test_emit_aborts_on_non_tty(self) -> None:
        """emit with non-TTY stdin should abort before any browser interaction."""
        from nfse_emit import cmd_emit

        # Simulate non-TTY stdin
        fake_stdin = io.StringIO("EMITIR\n")

        with (
            patch.object(sys, "stdin", fake_stdin),
            patch("nfse_emit._load_cfg") as mock_cfg,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_cfg.return_value = MagicMock()
            cmd_emit._confirmed = True  # type: ignore[attr-defined]
            cmd_emit()

        assert exc_info.value.code == 1
