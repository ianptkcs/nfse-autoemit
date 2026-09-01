"""Tests for check_review: pure function, no browser needed."""

from __future__ import annotations

from nfse_config import NotaConfig
from nfse_wizard import ReviewSummary, check_review


def _make_cfg(**overrides: object) -> NotaConfig:
    defaults = {
        "tomador_cnpj": "11.222.333/0001-81",
        "valor": "1.500,00",
        "descricao_servico": "Datilografia",
        "codigo_tributacao": "170201",
        "municipio_prestacao": "Belo Horizonte",
        "municipio_uf": "MG",
        "competencia": "01/09/2026",
    }
    defaults.update(overrides)
    return NotaConfig(**defaults)  # type: ignore[arg-type]


def _make_summary(**overrides: object) -> ReviewSummary:
    defaults = {
        "tomador_cnpj": "11.222.333/0001-81",
        "tomador_nome": "Empresa Teste LTDA",
        "municipio": "Belo Horizonte/MG",
        "descricao_servico": "Datilografia",
        "valor": "1.500,00",
        "competencia": "01/09/2026",
    }
    defaults.update(overrides)
    return ReviewSummary(**defaults)  # type: ignore[arg-type]


class TestCheckReview:
    def test_no_divergences(self) -> None:
        cfg = _make_cfg()
        summary = _make_summary()
        assert check_review(summary, cfg) == []

    def test_cnpj_mismatch(self) -> None:
        cfg = _make_cfg()
        summary = _make_summary(tomador_cnpj="22.333.444/0002-55")
        divergences = check_review(summary, cfg)
        assert len(divergences) == 1
        assert "Tomador CNPJ" in divergences[0]

    def test_valor_mismatch(self) -> None:
        cfg = _make_cfg()
        summary = _make_summary(valor="2.000,00")
        divergences = check_review(summary, cfg)
        assert len(divergences) == 1
        assert "Valor" in divergences[0]

    def test_multiple_divergences(self) -> None:
        cfg = _make_cfg(tomador_nome_esperado="Empresa Certa")
        summary = _make_summary(
            tomador_cnpj="22.333.444/0002-55",
            valor="999,00",
            tomador_nome="Empresa Errada",
        )
        divergences = check_review(summary, cfg)
        assert len(divergences) == 3

    def test_nome_mismatch(self) -> None:
        cfg = _make_cfg(tomador_nome_esperado="Empresa Certa")
        summary = _make_summary(tomador_nome="Empresa Errada")
        divergences = check_review(summary, cfg)
        assert len(divergences) == 1
        assert "Tomador Nome" in divergences[0]

    def test_nome_not_validated_when_not_configured(self) -> None:
        cfg = _make_cfg(tomador_nome_esperado=None)
        summary = _make_summary(tomador_nome="Whatever")
        divergences = check_review(summary, cfg)
        assert divergences == []

    def test_empty_summary_fields_skipped(self) -> None:
        """Empty review fields are skipped (portal may not show them)."""
        cfg = _make_cfg()
        summary = ReviewSummary(
            tomador_cnpj="",
            tomador_nome="",
            municipio="",
            descricao_servico="",
            valor="",
            competencia="",
        )
        assert check_review(summary, cfg) == []
