"""All Playwright locators, grouped by wizard step.

The NFS-e portal uses Angular with repeated labels between sections
(emitente and tomador both have "CPF/CNPJ", "Nome/Razão Social").
All locators here are scoped to avoid ambiguity — never use global
``get_by_label`` without a container anchor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

LOGIN_URL = "/EmissorNacional/Login"


# ---------------------------------------------------------------------------
# Etapa 1 — Pessoas
# ---------------------------------------------------------------------------


class PessoasSelectors:
    """Locators for the Pessoas step."""

    @staticmethod
    def radio_ibs_cbs(page: Page) -> Locator:
        """Radio 'Preencher as informações IBS/CBS?'."""
        return page.get_by_label("Não", exact=True).first

    @staticmethod
    def data_competencia(page: Page) -> Locator:
        """Date picker 'Data de Competência'."""
        return page.get_by_label("Data de Competência")

    @staticmethod
    def radio_compra_governamental(page: Page) -> Locator:
        """Radio 'A operação se trata de uma compra governamental?'."""
        return page.get_by_label("Não", exact=True).nth(1)

    @staticmethod
    def tomador_cnpj(page: Page) -> Locator:
        """CNPJ field in the Tomador section."""
        # Anchor to the Tomador section heading
        section = page.locator("section", has=page.get_by_text("Tomador/Adquirente do Serviço"))
        return section.get_by_label("CPF/CNPJ")

    @staticmethod
    def tomador_nome(page: Page) -> Locator:
        """Nome/Razão Social in the Tomador section."""
        section = page.locator("section", has=page.get_by_text("Tomador/Adquirente do Serviço"))
        return section.get_by_label("Nome/Razão Social")

    @staticmethod
    def historico_button(page: Page) -> Locator:
        """Button that opens the HISTÓRICO modal (people icon)."""
        section = page.locator("section", has=page.get_by_text("Tomador/Adquirente do Serviço"))
        return section.locator(
            "[aria-label*='Histórico'], [title*='Histórico'], button:has-text('Histórico')"
        ).first

    @staticmethod
    def historico_modal(page: Page) -> Locator:
        """The HISTÓRICO modal dialog."""
        return page.locator("[role='dialog'], .modal").filter(has_text="HISTÓRICO")

    @staticmethod
    def historico_row(page: Page, cnpj_digits: str) -> Locator:
        """A specific row in the HISTÓRICO table by CNPJ digits."""
        modal = PessoasSelectors.historico_modal(page)
        return modal.locator("tr").filter(has_text=cnpj_digits)

    @staticmethod
    def historico_importar(page: Page) -> Locator:
        """Importar button in the HISTÓRICO modal."""
        modal = PessoasSelectors.historico_modal(page)
        return modal.get_by_role("button", name="Importar")

    @staticmethod
    def radio_destinatario(page: Page) -> Locator:
        """Radio 'Para fins de apuração do IBS/CBS, o destinatário é o próprio adquirente?'."""
        return page.get_by_label("Sim", exact=True).first

    @staticmethod
    def btn_avancar(page: Page) -> Locator:
        """Avançar button at the end of the Pessoas step."""
        return page.get_by_role("button", name="Avançar")


# ---------------------------------------------------------------------------
# Etapa 2 — Serviço
# ---------------------------------------------------------------------------


class ServicoSelectors:
    """Locators for the Serviço step."""

    @staticmethod
    def municipio(page: Page) -> Locator:
        """Município searchable select in the service location section."""
        section = page.locator("section", has=page.get_by_text("Local do Fornecimento"))
        return section.get_by_label("Município")

    @staticmethod
    def codigo_tributacao(page: Page) -> Locator:
        """Código de Tributação Nacional searchable select."""
        return page.get_by_label("Código de Tributação Nacional")

    @staticmethod
    def radio_imunidade(page: Page) -> Locator:
        """Radio about imunidade/exportação/não incidência."""
        return page.get_by_label("Não", exact=True).first

    @staticmethod
    def descricao_servico(page: Page) -> Locator:
        """Textarea 'Descrição do Serviço/Fornecimento'."""
        return page.get_by_label("Descrição do Serviço/Fornecimento")

    @staticmethod
    def btn_avancar(page: Page) -> Locator:
        """Avançar button at the end of the Serviço step."""
        return page.get_by_role("button", name="Avançar")


# ---------------------------------------------------------------------------
# Etapa 3 — Valores/Tributação
# ---------------------------------------------------------------------------


class TributacaoSelectors:
    """Locators for the Tributação step."""

    @staticmethod
    def valor_operacao(page: Page) -> Locator:
        """'Valor da operação/serviço prestado' masked input."""
        return page.get_by_label("Valor da operação/serviço prestado")

    @staticmethod
    def radio_issqn_suspensa(page: Page) -> Locator:
        """Radio 'A exigibilidade do recolhimento do ISSQN... está suspensa?'."""
        return page.get_by_label("Não", exact=True).nth(0)

    @staticmethod
    def radio_retencao_issqn(page: Page) -> Locator:
        """Radio 'Há retenção do ISSQN pelo Tomador...?'."""
        return page.get_by_label("Não", exact=True).nth(1)

    @staticmethod
    def radio_beneficio_municipal(page: Page) -> Locator:
        """Radio 'Este serviço prestado está amparado por algum benefício municipal?'."""
        return page.get_by_label("Não", exact=True).nth(2)

    @staticmethod
    def radio_deducao(page: Page) -> Locator:
        """Radio 'Será aplicado algum tipo de Dedução/Redução...?'."""
        return page.get_by_label("Não", exact=True).nth(3)

    @staticmethod
    def radio_valor_tributos(page: Page) -> Locator:
        """Radio 'Não informar nenhum valor estimado para os Tributos'."""
        return page.get_by_label("Não informar nenhum valor estimado para os Tributos")

    @staticmethod
    def btn_avancar(page: Page) -> Locator:
        """Avançar button at the end of the Tributação step."""
        return page.get_by_role("button", name="Avançar")


# ---------------------------------------------------------------------------
# Etapa 4 — Emitir NFS-e (Review)
# ---------------------------------------------------------------------------


class EmitirSelectors:
    """Locators for the Emitir NFS-e (review/submit) step."""

    @staticmethod
    def btn_emitir(page: Page) -> Locator:
        """The 'Emitir NFS-e' button — only place this button is referenced."""
        return page.get_by_role("button", name="Emitir NFS-e")

    @staticmethod
    def secao_pessoas(page: Page) -> Locator:
        """Review section for Pessoas."""
        return page.locator("section", has=page.get_by_text("Pessoas"))

    @staticmethod
    def secao_servico(page: Page) -> Locator:
        """Review section for Serviço."""
        return page.locator("section", has=page.get_by_text("Serviço"))

    @staticmethod
    def secao_tributacao(page: Page) -> Locator:
        """Review section for Tributação."""
        return page.locator("section", has=page.get_by_text("Tributação"))

    @staticmethod
    def previa_valores(page: Page) -> Locator:
        """The PRÉVIA DOS VALORES DA NFS-E section."""
        return page.locator("section", has=page.get_by_text("PRÉVIA DOS VALORES DA NFS-E"))
