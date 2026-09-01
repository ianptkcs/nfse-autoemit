"""Form filling logic: fill_pessoas, fill_servico, fill_tributacao, read_review."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nfse_browser import (
    check_session,
    ensure_radio,
    fill_masked,
    select_searchable,
)
from nfse_config import NotaConfig, redact
from nfse_selectors import EmitirSelectors, PessoasSelectors, ServicoSelectors, TributacaoSelectors

if TYPE_CHECKING:
    from playwright.sync_api import Page

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Review summary (pure data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewSummary:
    """Data extracted from the review page before submission."""

    tomador_cnpj: str
    tomador_nome: str
    municipio: str
    descricao_servico: str
    valor: str
    competencia: str


# ---------------------------------------------------------------------------
# Etapa 1 — Pessoas
# ---------------------------------------------------------------------------


def fill_pessoas(page: Page, cfg: NotaConfig) -> None:
    """Fill the Pessoas step of the NFS-e wizard.

    This is the most fragile step: auto-populated fields, a history modal,
    and unreliable municipality list loading.
    """
    log.info("Preenchendo etapa 1: Pessoas")

    # 1. Radio IBS/CBS -> "Não"
    ensure_radio(page, "Preencher as informações IBS/CBS?", "Não")

    # 2. Data de Competência
    data_field = PessoasSelectors.data_competencia(page)
    fill_masked(data_field, cfg.competencia)

    # 3. Radio "Você irá emitir esta NFS-e como?" — already "Prestador/Fornecedor", no action

    # 4. Emitente fields auto-populate — do NOT touch them

    # 5. Compra governamental -> "Não"
    ensure_radio(page, "A operação se trata de uma compra governamental?", "Não")

    # 6. Tomador section
    _fill_tomador(page, cfg)

    # 7. Destinatário -> "Sim"
    ensure_radio(
        page,
        "Para fins de apuração do IBS/CBS, o destinatário é o próprio adquirente?",
        "Sim",
    )

    # 8. Intermediário — already "Intermediário não informado", no action

    # 9. Avançar
    PessoasSelectors.btn_avancar(page).click()
    page.wait_for_url(lambda u: "/DPS/Servico" in u, timeout=cfg.timeout_ms)
    check_session(page)
    log.info("Etapa 1 concluída")


def _fill_tomador(page: Page, cfg: NotaConfig) -> None:
    """Fill the Tomador/Adquirente do Serviço section."""
    # Try the HISTÓRICO modal first (primary path for recurring tomador)
    cnpj_digits = cfg.tomador_cnpj.replace(".", "").replace("/", "").replace("-", "")

    historico_btn = PessoasSelectors.historico_button(page)
    if historico_btn.count() > 0 and historico_btn.is_visible():
        try:
            historico_btn.click()
            time.sleep(1)

            modal = PessoasSelectors.historico_modal(page)
            if modal.is_visible():
                row = PessoasSelectors.historico_row(page, cnpj_digits)
                if row.count() > 0:
                    # Select the row radio and import
                    row.locator("input[type='radio'], input[type='checkbox']").first.check()
                    time.sleep(0.3)
                    PessoasSelectors.historico_importar(page).click()
                    time.sleep(1)
                    log.info("Tomador importado do histórico")
                    return

                # Row not found — close modal and fallback to manual
                close_btn = modal.locator("button:has-text('Fechar'), button:has-text('Cancelar')")
                if close_btn.count() > 0:
                    close_btn.first.click()
                    time.sleep(0.5)
                log.warning(
                    "Tomador %s não encontrado no histórico, fallback manual",
                    redact(cfg.tomador_cnpj),
                )
        except Exception as exc:
            log.warning("Erro ao acessar histórico: %s", exc)

    # Fallback: type CNPJ manually
    cnpj_field = PessoasSelectors.tomador_cnpj(page)
    cnpj_field.click()
    cnpj_field.fill("")
    cnpj_field.press_sequentially(cnpj_digits, delay=50)
    time.sleep(1)  # wait for auto-populate from Receita

    # Verify Razão Social was populated
    nome_field = PessoasSelectors.tomador_nome(page)
    nome = nome_field.input_value()
    if not nome.strip():
        log.warning("Razão Social não auto-populou para CNPJ %s", redact(cfg.tomador_cnpj))
    else:
        log.info("Tomador: %s — %s", redact(cfg.tomador_cnpj), nome)


# ---------------------------------------------------------------------------
# Etapa 2 — Serviço
# ---------------------------------------------------------------------------


def fill_servico(page: Page, cfg: NotaConfig) -> None:
    """Fill the Serviço step."""
    log.info("Preenchendo etapa 2: Serviço")

    # 1. Município — searchable select
    municipio_field = ServicoSelectors.municipio(page)
    select_searchable(
        page,
        municipio_field,
        cfg.municipio_prestacao,
        cfg.municipio_label,
        timeout_ms=cfg.timeout_ms,
    )

    # 2. Código de Tributação Nacional — searchable select
    cod_field = ServicoSelectors.codigo_tributacao(page)
    # Portal shows "NN.NN.NN - Descrição" — type just the digits
    select_searchable(
        page,
        cod_field,
        cfg.codigo_tributacao,
        cfg.codigo_tributacao,  # option_label matched by prefix
        timeout_ms=cfg.timeout_ms,
    )

    # 3. Imunidade/exportação -> "Não"
    ensure_radio(page, "imunidade, exportação de serviço ou não incidência", "Não")

    # 4. Item da NBS — DELIBERATELY SKIPPED (optional despite asterisk)
    # The portal shows "Não informado" on the review page, which is fine.
    log.info("Campo 'Item da NBS' pulado deliberadamente (opcional)")

    # 5. Descrição do Serviço (textarea, required)
    desc_field = ServicoSelectors.descricao_servico(page)
    desc_field.fill(cfg.descricao_servico)

    # 6. Informações Complementares — all optional, skip

    # 7. Avançar
    ServicoSelectors.btn_avancar(page).click()
    page.wait_for_url(lambda u: "/DPS/Tributacao" in u, timeout=cfg.timeout_ms)
    check_session(page)
    log.info("Etapa 2 concluída")


# ---------------------------------------------------------------------------
# Etapa 3 — Valores/Tributação
# ---------------------------------------------------------------------------


def fill_tributacao(page: Page, cfg: NotaConfig) -> None:
    """Fill the Tributação step."""
    log.info("Preenchendo etapa 3: Tributação")

    # 1. Valor da operação — masked input
    valor_field = TributacaoSelectors.valor_operacao(page)
    fill_masked(valor_field, cfg.valor)

    # 2-4. Valor recebido, descontos — disabled/optional, skip

    # 5. Tributação Municipal — readonly for Simples Nacional
    # Confirm radios that default to "Não"
    ensure_radio(page, "exigibilidade do recolhimento do ISSQN", "Não")
    ensure_radio(page, "retenção do ISSQN", "Não")
    ensure_radio(page, "benefício municipal", "Não")
    ensure_radio(page, "Dedução/Redução", "Não")

    # 6. Tributação Federal — disabled for Simples Nacional, skip

    # 7. IBS/CBS — disabled (marked "Não" in step 1), skip

    # 8. Valor Aproximado dos Tributos — confirm default
    ensure_radio(
        page,
        "Não informar nenhum valor estimado",
        "Não informar nenhum valor estimado para os Tributos",
    )

    # 9. Avançar
    TributacaoSelectors.btn_avancar(page).click()
    page.wait_for_url(lambda u: "/DPS/EmitirNFSe" in u, timeout=cfg.timeout_ms)
    check_session(page)
    log.info("Etapa 3 concluída")


# ---------------------------------------------------------------------------
# Etapa 4 — Read Review
# ---------------------------------------------------------------------------


def read_review(page: Page) -> ReviewSummary:
    """Extract data from the review/summary page.

    Returns a ReviewSummary with all visible data for validation.
    """
    log.info("Lendo tela de revisão")

    # Extract Tomador data
    tomador_section = EmitirSelectors.secao_pessoas(page)
    tomador_text = tomador_section.inner_text() if tomador_section.count() > 0 else ""

    # Try to extract CNPJ and Nome from the review text
    import re

    cnpj_match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", tomador_text)
    tomador_cnpj = cnpj_match.group(1) if cnpj_match else ""

    # Nome is usually after "Nome/Razão Social" label
    nome_match = re.search(r"Nome/Razão Social\s*[:\n]\s*(.+?)(?:\n|$)", tomador_text)
    tomador_nome = nome_match.group(1).strip() if nome_match else ""

    # Extract Serviço data
    servico_section = EmitirSelectors.secao_servico(page)
    servico_text = servico_section.inner_text() if servico_section.count() > 0 else ""

    municipio_match = re.search(r"Município\s*[:\n]\s*(.+?)(?:\n|$)", servico_text)
    municipio = municipio_match.group(1).strip() if municipio_match else ""

    descricao_match = re.search(
        r"Descrição do Serviço.*?[:\n]\s*(.+?)(?:\n|$)", servico_text, re.DOTALL
    )
    descricao_servico = descricao_match.group(1).strip() if descricao_match else ""

    # Extract Valores
    tributacao_section = EmitirSelectors.secao_tributacao(page)
    tributacao_text = tributacao_section.inner_text() if tributacao_section.count() > 0 else ""

    valor_match = re.search(r"Valor da operação.*?[:\n]\s*R\$\s*(.+?)(?:\n|$)", tributacao_text)
    valor = valor_match.group(1).strip() if valor_match else ""

    competencia_match = re.search(r"Competência\s*[:\n]\s*(.+?)(?:\n|$)", tomador_text)
    competencia = competencia_match.group(1).strip() if competencia_match else ""

    summary = ReviewSummary(
        tomador_cnpj=tomador_cnpj,
        tomador_nome=tomador_nome,
        municipio=municipio,
        descricao_servico=descricao_servico,
        valor=valor,
        competencia=competencia,
    )

    log.info("Revisão extraída: tomador=%s, valor=%s", redact(tomador_cnpj), valor)
    return summary


def check_review(summary: ReviewSummary, cfg: NotaConfig) -> list[str]:
    """Compare review data against expected config.

    Returns a list of divergences. Any divergence = abort, never a warning.
    """
    divergences: list[str] = []

    # Only validate fields we care about (skip empty review fields — portal may not show them)
    if summary.tomador_cnpj and summary.tomador_cnpj != cfg.tomador_cnpj:
        divergences.append(
            f"Tomador CNPJ: esperado {redact(cfg.tomador_cnpj)}, "
            f"encontrado {redact(summary.tomador_cnpj)}"
        )

    if (
        summary.tomador_nome
        and cfg.tomador_nome_esperado
        and summary.tomador_nome != cfg.tomador_nome_esperado
    ):
        divergences.append(
            f"Tomador Nome: esperado {cfg.tomador_nome_esperado!r}, "
            f"encontrado {summary.tomador_nome!r}"
        )

    if summary.valor and summary.valor != cfg.valor:
        divergences.append(f"Valor: esperado {cfg.valor}, encontrado {summary.valor}")

    return divergences
