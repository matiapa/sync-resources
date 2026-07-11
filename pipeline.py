from pathlib import Path

from config import Config
from runlog import RunStats

MIN_NOTES_FOR_THRESHOLD = 5
STALE_RATIO_THRESHOLD = 0.5


def _frontmatter_source(path: Path) -> str | None:
    """Lee el valor del campo `source:` del frontmatter YAML, o None si no hay.

    No se usa un parser YAML: el formato de nota es fijo (un `---` inicial, un
    `---` de cierre, líneas `clave: valor`), así que un escaneo de texto simple
    alcanza y evita una dependencia nueva.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("source:"):
            return line[len("source:"):].strip()
    return None


def _delete_stale_notes(resources_dir: Path, source, fetched_stems: set, stats: RunStats) -> None:
    """Borra notas de `source` cuyo item ya no está en `fetched_stems`.

    Solo se consideran "owned" las notas cuyo frontmatter declara
    `source: <source.name>`, para no tocar notas agregadas a mano. Si el
    borrado alcanzaría más de la mitad de las notas owned (habiendo al menos
    MIN_NOTES_FOR_THRESHOLD), se aborta y se registra como error en vez de
    borrar: protege contra un fetch vacío o parcial por falla de la API (ese
    caso extremo cae en el mismo chequeo, porque ahí `stale == owned`, 100%).
    """
    if not resources_dir.exists():
        return
    owned = [p for p in resources_dir.glob("*.md") if _frontmatter_source(p) == source.name]
    stale = [p for p in owned if p.stem not in fetched_stems]
    if not stale:
        return
    if len(owned) >= MIN_NOTES_FOR_THRESHOLD and len(stale) / len(owned) > STALE_RATIO_THRESHOLD:
        stats.errors.append((
            f"<{source.name}>",
            f"borrado abortado: {len(stale)}/{len(owned)} notas superan el umbral del 50%",
        ))
        return
    for path in stale:
        try:
            path.unlink()
        except OSError as exc:
            stats.errors.append((path.stem, str(exc)))
            continue
        stats.deleted += 1
        stats.deleted_items.append(path.stem)


def process_source(cfg: Config, source, limit=None, progress=None) -> RunStats:
    """Sincroniza una fuente: escribe una nota por item nuevo y borra las de
    items des-faveados (unstar / unbookmark).

    La fuente de verdad de "ya procesado" es la existencia del archivo de nota;
    los items ya presentes se saltean sin llamar a ``render`` (así no se gasta
    en red ni en OpenAI). Los errores de ``render`` se registran y no cortan la
    corrida. Nunca se escriben archivos parciales. El borrado de notas
    des-faveadas usa el ``fetch()`` completo, sin acotar por ``limit``.
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

    fetched_stems = {source.stem(item) for item in items}
    _delete_stale_notes(resources_dir, source, fetched_stems, stats)
    return stats
