"""NotaConfig: env -> dataclass, normalização, validação, redaction."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://www.producaorestrita.nfse.gov.br"
DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_SLOW_MO_MS = 0

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _strip_mask(value: str) -> str:
    """Remove everything that is not a digit."""
    return re.sub(r"\D", "", value)


def _validate_cnpj(raw: str) -> str:
    """Validate CNPJ check digits and return the masked form ``XX.XXX.XXX/XXXX-XX``."""
    digits = _strip_mask(raw)
    if len(digits) != 14:
        raise ValueError(f"CNPJ deve ter 14 dígitos, recebeu {len(digits)}: {raw!r}")

    # known invalid patterns (all same digit)
    if len(set(digits)) == 1:
        raise ValueError(f"CNPJ inválido (todos dígitos iguais): {raw!r}")

    # check digits
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def _digit(nums: list[int], w: list[int]) -> int:
        s = sum(n * ww for n, ww in zip(nums, w, strict=True))
        r = s % 11
        return 0 if r < 2 else 11 - r

    ns = [int(c) for c in digits]
    d1 = _digit(ns[:12], weights1)
    d2 = _digit(ns[:13], weights2)
    if ns[12] != d1 or ns[13] != d2:
        raise ValueError(f"CNPJ com dígitos verificadores inválidos: {raw!r}")

    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _parse_valor(raw: str) -> str:
    """Normalize currency input to Brazilian format ``X.XXX,XX``."""
    if not raw.strip():
        raise ValueError("Valor não pode ser vazio")

    # Remove R$ prefix if present
    cleaned = raw.strip()
    if cleaned.upper().startswith("R$"):
        cleaned = cleaned[2:].strip()

    # Detect format: "2.000,00" (BR) vs "2000.00" (US) vs "2000,00" (BR no thousands)
    # If both . and , present: BR format (dots = thousands, comma = decimal)
    # If only ,: BR without thousands (comma = decimal)
    # If only .: could be US decimal or thousands — check context
    if "," in cleaned and "." in cleaned:
        # BR: 2.000,00 -> remove dots, comma becomes decimal point
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # BR without thousands: 2000,00 -> comma becomes decimal point
        cleaned = cleaned.replace(",", ".")
    else:
        # No comma: could be "2000" (integer) or "2000.00" (US decimal)
        # Keep as-is for float() parsing
        pass

    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"Valor inválido: {raw!r}") from None

    if value < 0:
        raise ValueError(f"Valor não pode ser negativo: {value}")

    # Format as Brazilian currency: 2.000,00
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _parse_competencia(raw: str, today: date | None = None) -> str:
    """Normalize competência to ``dd/mm/aaaa``. Empty -> today."""
    raw = raw.strip()
    if not raw:
        d = today or date.today()
        return d.strftime("%d/%m/%Y")

    # Already in dd/mm/aaaa
    if re.match(r"^\d{2}/\d{2}/\d{4}$", raw):
        return raw

    # Try mm/aaaa
    m = re.match(r"^(\d{2})/(\d{4})$", raw)
    if m:
        return f"01/{m.group(1)}/{m.group(2)}"

    # Try aaaa-mm-dd (ISO)
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
        return d.strftime("%d/%m/%Y")
    except ValueError:
        pass

    raise ValueError(
        f"Competência em formato inválido: {raw!r}. Use dd/mm/aaaa, mm/aaaa, ou aaaa-mm-dd."
    )


def _municipio_label(municipio: str, uf: str) -> str:
    """Format ``Município/UF`` label for the portal."""
    return f"{municipio.strip()}/{uf.strip().upper()}"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotaConfig:
    """Immutable configuration for a single NFS-e emission."""

    # Required
    tomador_cnpj: str
    valor: str
    descricao_servico: str
    codigo_tributacao: str
    municipio_prestacao: str
    municipio_uf: str

    # Optional / guards
    competencia: str
    emitente_cnpj: str | None = None
    tomador_nome_esperado: str | None = None

    # Environment
    base_url: str = DEFAULT_BASE_URL
    headless: bool = False
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    slow_mo_ms: int = DEFAULT_SLOW_MO_MS
    profile_dir: str | None = None
    artifact_dir: str | None = None
    cdp_url: str | None = None

    @property
    def municipio_label(self) -> str:
        """``Município/UF`` for the portal's searchable select."""
        return _municipio_label(self.municipio_prestacao, self.municipio_uf)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = [
    "NFSE_TOMADOR_CNPJ",
    "NFSE_VALOR",
    "NFSE_DESCRICAO_SERVICO",
    "NFSE_CODIGO_TRIBUTACAO",
    "NFSE_MUNICIPIO_PRESTACAO",
    "NFSE_MUNICIPIO_UF",
]


def load_config(env: Mapping[str, str]) -> NotaConfig:
    """Build a ``NotaConfig`` from an arbitrary mapping (testable, no os import).

    Collects *all* missing/invalid required fields before raising, so the user
    can fix multiple issues in one pass.
    """
    errors: list[str] = []

    def _get(key: str) -> str:
        val = env.get(key, "").strip()
        if not val:
            errors.append(f"Variável obrigatória ausente: {key}")
        return val

    # Required fields (collected even if empty, to report all errors)
    tomador_cnpj_raw = _get("NFSE_TOMADOR_CNPJ")
    valor_raw = _get("NFSE_VALOR")
    descricao_servico = _get("NFSE_DESCRICAO_SERVICO")
    codigo_tributacao = _get("NFSE_CODIGO_TRIBUTACAO")
    municipio = _get("NFSE_MUNICIPIO_PRESTACAO")
    uf = _get("NFSE_MUNICIPIO_UF")

    # Validate CNPJ if present
    tomador_cnpj = ""
    if tomador_cnpj_raw:
        try:
            tomador_cnpj = _validate_cnpj(tomador_cnpj_raw)
        except ValueError as e:
            errors.append(str(e))

    # Normalize valor if present
    valor = ""
    if valor_raw:
        try:
            valor = _parse_valor(valor_raw)
        except ValueError as e:
            errors.append(str(e))

    # Validate UF length
    if uf and len(uf) != 2:
        errors.append(f"UF deve ter 2 caracteres, recebeu {len(uf)}: {uf!r}")

    if errors:
        raise ValueError("Erros de configuração:\n" + "\n".join(f"  - {e}" for e in errors))

    # Optional fields
    competencia = _parse_competencia(env.get("NFSE_COMPETENCIA", ""))
    emitente_cnpj_raw = env.get("NFSE_EMITENTE_CNPJ", "").strip()
    emitente_cnpj: str | None = None
    if emitente_cnpj_raw:
        try:
            emitente_cnpj = _validate_cnpj(emitente_cnpj_raw)
        except ValueError as e:
            errors.append(str(e))
            if errors:
                raise ValueError(
                    "Erros de configuração:\n" + "\n".join(f"  - {e}" for e in errors)
                ) from e

    tomador_nome_raw = env.get("NFSE_TOMADOR_NOME_ESPERADO", "").strip()
    tomador_nome: str | None = tomador_nome_raw or None

    # Environment settings
    base_url = env.get("NFSE_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    headless = env.get("NFSE_HEADLESS", "0").strip() in ("1", "true", "True")
    timeout_str = env.get("NFSE_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)).strip()
    timeout_ms = int(timeout_str) if timeout_str.isdigit() else DEFAULT_TIMEOUT_MS
    slow_mo_str = env.get("NFSE_SLOW_MO_MS", str(DEFAULT_SLOW_MO_MS)).strip()
    slow_mo_ms = int(slow_mo_str) if slow_mo_str.isdigit() else DEFAULT_SLOW_MO_MS
    profile_dir = env.get("NFSE_PROFILE_DIR", "").strip() or None
    artifact_dir = env.get("NFSE_ARTIFACT_DIR", "").strip() or None
    cdp_url = env.get("NFSE_CDP_URL", "").strip() or None

    return NotaConfig(
        tomador_cnpj=tomador_cnpj,
        valor=valor,
        descricao_servico=descricao_servico,
        codigo_tributacao=codigo_tributacao,
        municipio_prestacao=municipio,
        municipio_uf=uf.upper(),
        competencia=competencia,
        emitente_cnpj=emitente_cnpj,
        tomador_nome_esperado=tomador_nome,
        base_url=base_url,
        headless=headless,
        timeout_ms=timeout_ms,
        slow_mo_ms=slow_mo_ms,
        profile_dir=profile_dir,
        artifact_dir=artifact_dir,
        cdp_url=cdp_url,
    )


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_RAW_CNPJ_RE = re.compile(r"(?<!\d)\d{14}(?!\d)")
_RAW_CPF_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")


def redact(text: str) -> str:
    """Mask CNPJ/CPF in arbitrary text for safe logging."""
    result = _CNPJ_RE.sub(lambda m: m.group()[:2] + ".XXX.XXX/" + "XXXX" + "-" + "XX", text)
    result = _CPF_RE.sub(lambda m: m.group()[:3] + ".XXX.XXX-" + "XX", result)
    # Raw 14-digit CNPJ (only if not already masked)
    result = _RAW_CNPJ_RE.sub(lambda m: m.group()[:2] + "XXXXXXXXXXXX" + m.group()[-2:], result)
    # Raw 11-digit CPF (only if not already masked)
    return _RAW_CPF_RE.sub(lambda m: m.group()[:3] + "XXXXXXX" + m.group()[-2:], result)


# ---------------------------------------------------------------------------
# CLI (minimal, for quick smoke test)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    import os

    try:
        cfg = load_config(os.environ)
        print(f"Config OK: tomador={redact(cfg.tomador_cnpj)}, valor={cfg.valor}")
        print(f"  município: {cfg.municipio_label}")
        print(f"  competência: {cfg.competencia}")
        print(f"  base_url: {cfg.base_url}")
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
