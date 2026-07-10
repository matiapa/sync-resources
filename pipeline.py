from config import Config
from runlog import RunStats


def process_source(cfg: Config, source, limit=None, progress=None) -> RunStats:
    """Sincroniza una fuente: escribe una nota por item nuevo.

    La fuente de verdad de "ya procesado" es la existencia del archivo de nota;
    los items ya presentes se saltean sin llamar a ``render`` (así no se gasta
    en red ni en OpenAI). Los errores de ``render`` se registran y no cortan la
    corrida. Nunca se escriben archivos parciales.
    """
    stats = RunStats()
    resources_dir = cfg.digital_brain_path / source.subdir
    items = source.fetch()
    iterable = items if progress is None else progress(items)
    for item in iterable:
        if limit is not None and stats.created >= limit:
            break
        stats.seen += 1
        path = resources_dir / (source.stem(item) + ".md")
        if path.exists():
            stats.skipped += 1
            continue
        try:
            note = source.render(item)
            resources_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(note.text, encoding="utf-8")
            stats.tokens += note.tokens
            stats.created += 1
        except Exception as exc:  # noqa: BLE001 - se loguea y se sigue
            stats.errors.append((source.stem(item), str(exc)))
    return stats
