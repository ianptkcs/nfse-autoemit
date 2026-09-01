"""CLI entry point: login | config | preview | emit.

Invoked as: ``uv run bin/nfse_emit.py <subcommand>``
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from nfse_browser import (
    _CDP_PORT,
    close_browser,
    is_session_expired,
    launch_browser,
    launch_brave_with_cdp,
    is_brave_running,
    is_cdp_enabled,
    kill_brave,
)
from nfse_config import NotaConfig, load_config, redact
from nfse_submit import submit
from nfse_wizard import (
    check_review,
    fill_pessoas,
    fill_servico,
    fill_tributacao,
    read_review,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_cfg() -> NotaConfig:
    load_dotenv()
    return load_config(os.environ)


def _save_screenshot(page: object, path: Path) -> None:
    """Save a full-page screenshot."""
    try:
        from playwright.sync_api import Page

        if isinstance(page, Page):
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=True)
            log.info("Screenshot salvo: %s", path)
    except Exception as exc:
        log.warning("Falha ao salvar screenshot: %s", exc)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_config() -> None:
    """Print the loaded configuration (dry-run, no browser)."""
    cfg = _load_cfg()
    print(f"Tomador CNPJ:  {redact(cfg.tomador_cnpj)}")
    print(f"Valor:         R$ {cfg.valor}")
    print(f"Competência:   {cfg.competencia}")
    print(f"Município:     {cfg.municipio_label}")
    print(f"Cód. Tribut.:  {cfg.codigo_tributacao}")
    print(f"Descrição:     {cfg.descricao_servico}")
    print(f"Base URL:      {cfg.base_url}")
    print(f"Headless:      {cfg.headless}")
    print(f"Timeout:       {cfg.timeout_ms}ms")


def cmd_login() -> None:
    """Open Brave with remote debugging for manual gov.br login.

    Uses the user's real Brave profile (cookies, extensions, etc.)
    for maximum compatibility with gov.br's bot detection.
    """
    cfg = _load_cfg()

    # Check if CDP is already enabled
    if is_cdp_enabled():
        print("Brave já está rodando com remote debugging.")
    elif is_brave_running():
        print("Brave está rodando SEM remote debugging.")
        print("")
        answer = (
            input("Preciso fechar e reabrir com remote debugging. Pode fechar? (s/N): ")
            .strip()
            .lower()
        )
        if answer not in ("s", "sim", "y", "yes"):
            print("Cancelado. Feche o Brave manualmente e rode novamente.")
            return
        print("Fechando Brave...")
        kill_brave()
        print("Iniciando Brave com remote debugging...")
        if not launch_brave_with_cdp():
            print("ERRO: Não foi possível iniciar Brave com remote debugging.")
            return
    else:
        print("Brave não está rodando. Iniciando com remote debugging...")
        if not launch_brave_with_cdp():
            print("ERRO: Não foi possível iniciar Brave.")
            return

    print("")
    print("PASSO A PASSO:")
    print("  1. No Brave, navegue até o Emissor Nacional")
    print("  2. Faça o login manualmente (gov.br)")
    print("  3. Quando estiver logado, volte aqui e pressione Enter")
    print("")

    # Update config to use CDP
    from dataclasses import replace

    cdp_cfg = replace(cfg, cdp_url=f"http://localhost:{_CDP_PORT}")

    context = launch_browser(cdp_cfg)
    page = context.pages[0]

    try:
        page.goto(f"{cfg.base_url}/EmissorNacional/Login", timeout=cfg.timeout_ms)
        print(f"Conectado em: {page.url}")
        input(">>> Pressione ENTER quando estiver logado no Emissor Nacional... ")
        print("Sessão mantida no Brave. Pode usar preview/emit agora.")
    finally:
        close_browser(context)


def cmd_preview() -> None:
    """Run the wizard up to the review page (dry-run, no emission)."""
    cfg = _load_cfg()
    artifact_dir = (
        Path(cfg.artifact_dir)
        if cfg.artifact_dir
        else Path.home() / ".local" / "state" / "nfse-autoemit" / "artifacts"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    context = launch_browser(cfg)
    # Use the first page from the persistent context
    page = context.pages[0]

    try:
        # Navigate to start
        page.goto(f"{cfg.base_url}/EmissorNacional/DPS/Pessoas", timeout=cfg.timeout_ms)

        # Check session
        if is_session_expired(page):
            print("Sessão não encontrada ou expirada.")
            print("")
            print("Execute primeiro: uv run bin/nfse_emit.py login")
            print("Faça o login manualmente e depois volte para o preview.")
            return

        # Run wizard steps with retry
        from nfse_browser import retry_step

        retry_step(page, lambda p: fill_pessoas(p, cfg))
        retry_step(page, lambda p: fill_servico(p, cfg))
        retry_step(page, lambda p: fill_tributacao(p, cfg))

        # Read review
        summary = read_review(page)

        # Validate
        divergences = check_review(summary, cfg)
        if divergences:
            print("DIVERGÊNCIAS ENCONTRADAS:")
            for d in divergences:
                print(f"  - {d}")
            print("ABORTANDO: corrija o .env e tente novamente.")
            sys.exit(1)

        # Print summary
        print("\n=== REVISÃO DA NFS-e ===")
        print(f"Tomador:  {redact(summary.tomador_cnpj)} — {summary.tomador_nome}")
        print(f"Município: {summary.municipio}")
        print(f"Serviço:  {summary.descricao_servico}")
        print(f"Valor:    R$ {summary.valor}")
        print(f"Competência: {summary.competencia}")
        print("========================\n")

        # Save screenshot
        screenshot_path = artifact_dir / "preview-review.png"
        _save_screenshot(page, screenshot_path)

        print("Preview concluído. Nenhuma NFS-e foi emitida.")
        print(f"Screenshot: {screenshot_path}")

    except Exception as exc:
        log.error("Erro durante preview: %s", exc)
        _save_screenshot(page, artifact_dir / "error-preview.png")
        raise
    finally:
        close_browser(context)


def cmd_emit() -> None:
    """Emit the NFS-e — requires --confirm AND typing EMITIR."""
    cfg = _load_cfg()

    # Gate 1: --confirm flag
    if not getattr(cmd_emit, "_confirmed", False):
        print("ERRO: use 'uv run bin/nfse_emit.py emit --confirm'")
        sys.exit(1)

    # Gate 2: stdin must be TTY
    if not sys.stdin.isatty():
        print("ERRO: emit requer terminal interativo (TTY).")
        print("Não é possível emitir de dentro de um cron/script.")
        sys.exit(1)

    # Gate 3: type EMITIR
    print("⚠️  ATENÇÃO: você está prestes a emitir uma NFS-e real.")
    print("Esta ação NÃO pode ser desfeita.")
    print()
    answer = input("Digite EMITIR para confirmar: ").strip()
    if answer != "EMITIR":
        print("Confirmação cancelada.")
        sys.exit(1)

    artifact_dir = (
        Path(cfg.artifact_dir)
        if cfg.artifact_dir
        else Path.home() / ".local" / "state" / "nfse-autoemit" / "artifacts"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    context = launch_browser(cfg)
    # Use the first page from the persistent context
    page = context.pages[0]

    try:
        # Navigate to start
        page.goto(f"{cfg.base_url}/EmissorNacional/DPS/Pessoas", timeout=cfg.timeout_ms)

        # Check session
        if is_session_expired(page):
            print("Sessão não encontrada ou expirada.")
            print("")
            print("Execute primeiro: uv run bin/nfse_emit.py login")
            print("Faça o login manualmente e depois volte para emitir.")
            return

        # Run wizard steps with retry
        from nfse_browser import retry_step

        retry_step(page, lambda p: fill_pessoas(p, cfg))
        retry_step(page, lambda p: fill_servico(p, cfg))
        retry_step(page, lambda p: fill_tributacao(p, cfg))

        # Read review
        summary = read_review(page)

        # Validate
        divergences = check_review(summary, cfg)
        if divergences:
            print("DIVERGÊNCIAS ENCONTRADAS — ABORTANDO:")
            for d in divergences:
                print(f"  - {d}")
            sys.exit(1)

        # Final confirmation prompt
        print("\n=== CONFIRMAÇÃO FINAL ===")
        print(f"Tomador:  {redact(summary.tomador_cnpj)} — {summary.tomador_nome}")
        print(f"Valor:    R$ {summary.valor}")
        print("=========================\n")

        # Submit
        nfse_number = submit(page, summary, confirmed=True)

        # Save artifacts
        _save_screenshot(page, artifact_dir / "emission-success.png")

        if nfse_number:
            print(f"\n✅ NFS-e emitida com sucesso! Nº: {nfse_number}")
        else:
            print("\n✅ NFS-e submetida (número não capturado automaticamente).")

        print(f"Screenshot: {artifact_dir / 'emission-success.png'}")

    except Exception as exc:
        log.error("Erro durante emissão: %s", exc)
        _save_screenshot(page, artifact_dir / "error-emission.png")
        raise
    finally:
        close_browser(context)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="NFS-e Autoemit: automação de preenchimento do Emissor Nacional",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("config", help="Mostra a configuração carregada (sem browser)")
    sub.add_parser("login", help="Abre o portal para login manual no gov.br")
    sub.add_parser("preview", help="Executa o wizard até a revisão (dry-run)")
    emit_parser = sub.add_parser("emit", help="Emite a NFS-e (requer confirmação)")
    emit_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Primeira porta de confirmação para emissão",
    )

    args = parser.parse_args()

    if args.command == "config":
        cmd_config()
    elif args.command == "login":
        cmd_login()
    elif args.command == "preview":
        cmd_preview()
    elif args.command == "emit":
        cmd_emit._confirmed = args.confirm  # type: ignore[attr-defined]
        cmd_emit()


if __name__ == "__main__":
    main()
