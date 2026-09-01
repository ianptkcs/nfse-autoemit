"""Tests for nfse_config: normalizations, aggregated errors, redaction."""

from __future__ import annotations

import pytest

from nfse_config import (
    NotaConfig,
    _municipio_label,
    _parse_competencia,
    _parse_valor,
    _validate_cnpj,
    load_config,
    redact,
)

# ---------------------------------------------------------------------------
# CNPJ validation
# ---------------------------------------------------------------------------


class TestCNPJValidation:
    def test_valid_cnpj_masked(self) -> None:
        result = _validate_cnpj("11.222.333/0001-81")
        assert result == "11.222.333/0001-81"

    def test_valid_cnpj_digits(self) -> None:
        result = _validate_cnpj("11222333000181")
        assert result == "11.222.333/0001-81"

    def test_invalid_check_digit(self) -> None:
        with pytest.raises(ValueError, match="dígitos verificadores inválidos"):
            _validate_cnpj("11.222.333/0001-00")

    def test_too_short(self) -> None:
        with pytest.raises(ValueError, match="14 dígitos"):
            _validate_cnpj("123456")

    def test_all_same_digit(self) -> None:
        with pytest.raises(ValueError, match="dígitos iguais"):
            _validate_cnpj("11.111.111/1111-11")

    def test_letters(self) -> None:
        with pytest.raises(ValueError, match="14 dígitos"):
            _validate_cnpj("abcdefghij")


# ---------------------------------------------------------------------------
# Valor normalization
# ---------------------------------------------------------------------------


class TestParseValor:
    def test_integer(self) -> None:
        assert _parse_valor("2000") == "2.000,00"

    def test_float_dot(self) -> None:
        assert _parse_valor("2000.00") == "2.000,00"

    def test_float_comma(self) -> None:
        assert _parse_valor("2000,00") == "2.000,00"

    def test_brazilian_format(self) -> None:
        assert _parse_valor("2.000,00") == "2.000,00"

    def test_with_rs_prefix(self) -> None:
        assert _parse_valor("R$ 2000") == "2.000,00"

    def test_small_value(self) -> None:
        assert _parse_valor("150,50") == "150,50"

    def test_zero(self) -> None:
        assert _parse_valor("0") == "0,00"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="vazio"):
            _parse_valor("")

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="negativo"):
            _parse_valor("-100")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="inválido"):
            _parse_valor("abc")


# ---------------------------------------------------------------------------
# Competência normalization
# ---------------------------------------------------------------------------


class TestParseCompetencia:
    def test_empty_uses_today(self) -> None:
        result = _parse_competencia("")
        assert "/" in result
        assert len(result) == 10  # dd/mm/aaaa

    def test_dd_mm_aaaa(self) -> None:
        assert _parse_competencia("15/06/2026") == "15/06/2026"

    def test_mm_aaaa(self) -> None:
        assert _parse_competencia("06/2026") == "01/06/2026"

    def test_iso_date(self) -> None:
        assert _parse_competencia("2026-06-15") == "15/06/2026"

    def test_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="inválido"):
            _parse_competencia("15-06-2026")


# ---------------------------------------------------------------------------
# Municipio label
# ---------------------------------------------------------------------------


class TestMunicipioLabel:
    def test_basic(self) -> None:
        assert _municipio_label("Belo Horizonte", "MG") == "Belo Horizonte/MG"

    def test_strips_whitespace(self) -> None:
        assert _municipio_label("  São Paulo  ", "sp") == "São Paulo/SP"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

_MINIMAL_ENV = {
    "NFSE_TOMADOR_CNPJ": "11.222.333/0001-81",
    "NFSE_VALOR": "1500",
    "NFSE_DESCRICAO_SERVICO": "Datilografia",
    "NFSE_CODIGO_TRIBUTACAO": "170201",
    "NFSE_MUNICIPIO_PRESTACAO": "Belo Horizonte",
    "NFSE_MUNICIPIO_UF": "MG",
}


class TestLoadConfig:
    def test_minimal(self) -> None:
        cfg = load_config(_MINIMAL_ENV)
        assert isinstance(cfg, NotaConfig)
        assert cfg.tomador_cnpj == "11.222.333/0001-81"
        assert cfg.valor == "1.500,00"
        assert cfg.municipio_label == "Belo Horizonte/MG"

    def test_missing_required_aggregates_errors(self) -> None:
        with pytest.raises(ValueError, match="ausente") as exc_info:
            load_config({})
        msg = str(exc_info.value)
        # All required fields reported
        assert "NFSE_TOMADOR_CNPJ" in msg
        assert "NFSE_VALOR" in msg
        assert "NFSE_DESCRICAO_SERVICO" in msg
        assert "NFSE_CODIGO_TRIBUTACAO" in msg
        assert "NFSE_MUNICIPIO_PRESTACAO" in msg
        assert "NFSE_MUNICIPIO_UF" in msg

    def test_invalid_cnpj_reported(self) -> None:
        env = {**_MINIMAL_ENV, "NFSE_TOMADOR_CNPJ": "123"}
        with pytest.raises(ValueError, match="14 dígitos"):
            load_config(env)

    def test_uf_too_long(self) -> None:
        env = {**_MINIMAL_ENV, "NFSE_MUNICIPIO_UF": "MGX"}
        with pytest.raises(ValueError, match="2 caracteres"):
            load_config(env)

    def test_optional_fields(self) -> None:
        env = {
            **_MINIMAL_ENV,
            "NFSE_COMPETENCIA": "06/2026",
            "NFSE_EMITENTE_CNPJ": "11.222.333/0001-81",
            "NFSE_TOMADOR_NOME_ESPERADO": "Empresa Teste",
            "NFSE_HEADLESS": "1",
            "NFSE_TIMEOUT_MS": "30000",
        }
        cfg = load_config(env)
        assert cfg.competencia == "01/06/2026"
        assert cfg.emitente_cnpj == "11.222.333/0001-81"
        assert cfg.tomador_nome_esperado == "Empresa Teste"
        assert cfg.headless is True
        assert cfg.timeout_ms == 30000


# ---------------------------------------------------------------------------
# redact
# ---------------------------------------------------------------------------


class TestRedact:
    def test_masked_cnpj(self) -> None:
        result = redact("CNPJ: 11.222.333/0001-81")
        assert "11.XXX.XXX/XXXX-XX" in result

    def test_masked_cpf(self) -> None:
        result = redact("CPF: 123.456.789-00")
        assert "123.XXX.XXX-XX" in result

    def test_no_false_positives(self) -> None:
        text = "Código: 1234, valor: 5678"
        assert redact(text) == text

    def test_preserves_surrounding_text(self) -> None:
        text = "Nota para 11.222.333/0001-81 emitida"
        result = redact(text)
        assert result.startswith("Nota para ")
        assert result.endswith(" emitida")
