import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

import downstream
from config import ConfigError, load_config
from pipeline import process_source
from runlog import append_log, format_summary
from sources.github.source import GitHubSource


def build_sources(cfg, openai_client) -> list:
    return [GitHubSource(cfg, openai_client)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza recursos externos (repos faveados, ...) al digital brain."
    )
    parser.add_argument(
        "--source",
        choices=["github"],
        default=None,
        help="Correr solo una fuente (default: todas).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como máximo N items nuevos por fuente (corrida de prueba).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=cfg.openai_api_key)
    sources = build_sources(cfg, client)
    if args.source:
        sources = [s for s in sources if s.name.lower() == args.source]

    exit_code = 0
    for source in sources:
        # disable=None apaga la barra en no-TTY (cron), evitando ensuciar sync.log.
        progress = lambda it, s=source: tqdm(
            it, desc=f"Sincronizando {s.name}", unit="item", disable=None
        )
        stats = process_source(cfg, source, limit=args.limit, progress=progress)

        if stats.created > 0:
            try:
                downstream.git_commit_push(
                    cfg.digital_brain_path,
                    source.subdir,
                    f"chore: sync {stats.created} {source.name} nuevos",
                    push=cfg.git_push,
                )
                stats.git_ok = True
            except Exception as exc:  # noqa: BLE001
                stats.git_ok = False
                stats.errors.append(("<git>", str(exc)))
            stats.gbrain_ok = downstream.gbrain_sync(cfg.digital_brain_path, cfg.gbrain_sync)

        summary_text = format_summary(stats, datetime.now())
        append_log(cfg.log_path, summary_text)
        print(summary_text, end="")
        if stats.result == "FALLO":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
