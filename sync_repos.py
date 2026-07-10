import argparse
import sys
from datetime import datetime
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

import downstream
import github_client
import notes
import summarizer
from config import Config, ConfigError, load_config
from runlog import RunStats, append_log, format_summary


def process_repos(cfg: Config, repos, deps, limit=None, progress=None) -> RunStats:
    stats = RunStats()
    resources_dir = cfg.digital_brain_path / cfg.github_subdir
    iterable = repos if progress is None else progress(repos)
    for repo in iterable:
        if limit is not None and stats.created >= limit:
            break
        stats.seen += 1
        if deps.note_exists(resources_dir, repo.full_name):
            stats.skipped += 1
            continue
        try:
            text = deps.get_readme(repo.full_name) or repo.description or repo.full_name
            summary, tokens = deps.summarize(repo.full_name, text)
            deps.write_note(resources_dir, repo, summary)
            stats.tokens += tokens
            stats.created += 1
        except Exception as exc:  # noqa: BLE001 - se loguea y se sigue
            stats.errors.append((repo.full_name, str(exc)))
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza repos faveados de GitHub a notas del digital brain."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como máximo N repos nuevos (útil para una corrida de prueba).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=cfg.openai_api_key)
    deps = SimpleNamespace(
        get_readme=lambda fn: github_client.get_readme(fn),
        summarize=lambda fn, text: summarizer.summarize(fn, text, cfg.openai_model, client),
        note_exists=notes.note_exists,
        write_note=notes.write_note,
    )

    repos = github_client.get_starred_repos()
    # disable=None desactiva la barra en no-TTY (ej. cron), evitando ensuciar sync.log.
    progress = lambda it: tqdm(it, desc="Sincronizando repos", unit="repo", disable=None)
    stats = process_repos(cfg, repos, deps, limit=args.limit, progress=progress)

    if stats.created > 0:
        try:
            downstream.git_commit_push(
                cfg.digital_brain_path,
                cfg.github_subdir,
                f"chore: sync {stats.created} repos faveados nuevos",
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
    return 1 if stats.result == "FALLO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
