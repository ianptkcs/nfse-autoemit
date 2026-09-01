"""Tests for no secrets in source code.

Scans bin/, tests/, README*.md, .env.example for real CNPJ/CPF patterns.
Allowlisted: test fixtures (00.000.000/0001-91, 11.222.333/0001-81, etc.)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Patterns that look like real CPF/CNPJ
_CNPJ_PATTERN = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_CPF_PATTERN = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_RAW_14 = re.compile(r"(?<!\d)\d{14}(?!\d)")
_RAW_11 = re.compile(r"(?<!\d)\d{11}(?!\d)")

# Allowlisted test fixtures
_ALLOWLIST = {
    "00.000.000/0001-91",  # Fictional CNPJ for tests
    "11.222.333/0001-81",  # Fictional CNPJ for tests
    "11.222.333/0001-00",  # Fictional CNPJ for tests (invalid check digits)
    "11.111.111/1111-11",  # Fictional CNPJ for tests (all same digit)
    "22.333.444/0002-55",  # Fictional CNPJ for tests
    "123.456.789-00",  # Fictional CPF for tests
}


def _scan_file(path: Path) -> list[str]:
    """Return matches that are not in the allowlist."""
    content = path.read_text(errors="ignore")
    found = []

    for m in _CNPJ_PATTERN.finditer(content):
        if m.group() not in _ALLOWLIST:
            found.append(f"{path.name}:{m.start()}: CNPJ {m.group()}")

    for m in _CPF_PATTERN.finditer(content):
        if m.group() not in _ALLOWLIST:
            found.append(f"{path.name}:{m.start()}: CPF {m.group()}")

    return found


@pytest.mark.parametrize(
    "glob_pattern",
    [
        "bin/*.py",
        "tests/*.py",
        "tests/integration/*.py",
        "README*.md",
        ".env.example",
    ],
)
def test_no_secrets_in_files(glob_pattern: str) -> None:
    """Scan files for real CNPJ/CPF patterns."""
    files = list(REPO_ROOT.glob(glob_pattern))
    if not files:
        pytest.skip(f"No files matching {glob_pattern}")

    all_found: list[str] = []
    for f in files:
        all_found.extend(_scan_file(f))

    assert not all_found, "Possíveis secrets encontrados:\n" + "\n".join(all_found)
