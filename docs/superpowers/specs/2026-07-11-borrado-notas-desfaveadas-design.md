# Borrado de notas de items des-faveados (GitHub unstar / X unbookmark)

**Fecha:** 2026-07-11
**Estado:** Aprobado (diseño)

## Objetivo

Hoy `pipeline.process_source` es solo aditivo: crea una nota por cada item
nuevo, pero nunca borra nada. Si el usuario le saca la estrella a un repo en
GitHub o remueve un post de sus guardados en X, la nota correspondiente queda
huérfana para siempre en el digital brain.

Este trabajo extiende el driver genérico para que, en cada corrida, borre las
notas cuyo item de origen ya no está entre los actualmente faveados/guardados,
para ambas fuentes (GitHub y X) sin duplicar lógica por fuente.

## Alcance

**Incluido:**
- Detección de notas "stale" (des-faveadas) por fuente, comparando el fetch
  actual contra los archivos `.md` existentes en el subdir de la fuente.
- Borrado de esas notas, con un guardrail de seguridad ante fallas
  transitorias de API que simulen un des-faveo masivo.
- Extensión de `RunStats`/`sync.log` para reportar borrados.
- El commit+push al digital brain y la reindexación GBrain se disparan también
  cuando la única novedad de la corrida son borrados.

**Fuera de alcance:**
- Papelera / soft-delete de notas borradas (se borran directo; el historial
  queda en git).
- Un flag `--apply-deletes` o modo dry-run explícito (se decidió no pedir
  confirmación manual; el guardrail de umbral cumple ese rol).
- Marcar de alguna forma especial en git el commit de borrado vs. creación
  (un solo commit combinado por fuente, igual que hoy).

## Enfoque

**Diff contra el filesystem, sin state file.** Igual que la detección de "ya
existe" hoy, la fuente de verdad sigue siendo el propio directorio de notas:
no se agrega una base de datos ni un manifiesto de "creado por mí". La
pertenencia de una nota a una fuente se determina leyendo su frontmatter
(`source: GitHub` / `source: X`), ya presente en el formato de nota actual.
Esto evita borrar notas que un usuario haya agregado a mano en el mismo
subdir con un nombre que coincida por casualidad con un stem.

Alternativas descartadas:
- **Manifiesto de stems creados** (archivo JSON con el set de items
  sincronizados): agrega un state file paralelo al filesystem, rompe la
  propiedad actual de "el vault es el estado", y hay que mantenerlo
  sincronizado con borrados/ediciones manuales del usuario en Obsidian.
- **Confiar en todo el subdir sin chequear frontmatter:** más simple, pero
  borraría sin aviso una nota que el usuario haya agregado a mano en
  `Recursos/Posts` o `Recursos/Repositorios` fuera del sync.

## Arquitectura

### Diff en `pipeline.process_source`

Tras el loop de creación existente (sin cambios), se agrega un paso de
borrado que opera sobre `items` (la lista completa devuelta por
`source.fetch()`, **no** acotada por `--limit`):

```
fetched_stems = {source.stem(item) for item in items}

owned = [p for p in resources_dir.glob("*.md")
         if _frontmatter_source(p) == source.name]
stale = [p for p in owned if p.stem not in fetched_stems]

if len(owned) >= MIN_NOTES_FOR_THRESHOLD and len(stale) / len(owned) > 0.5:
    errors.append((f"<{source.name}>",
                    f"borrado abortado: {len(stale)}/{len(owned)} notas "
                    f"superan el umbral del 50%"))
else:
    for p in stale:
        p.unlink()
        deleted += 1
        deleted_items.append(p.stem)
```

`MIN_NOTES_FOR_THRESHOLD = 5`: por debajo de ese piso el guardrail de
porcentaje no aplica (el blast radius de borrar unas pocas notas es
intrínsecamente chico, y con conteos bajos el porcentaje es ruidoso —
ej. borrar 1 de 2 ya es "50%").

El guardrail cubre también el caso "fetch devolvió vacío por una falla de
API": si `items == []`, entonces `stale == owned`, es decir 100% > 50%, y se
aborta igual que cualquier otro des-faveo masivo. No hace falta un chequeo
especial para la lista vacía.

`_frontmatter_source(path)` lee solo las primeras líneas del archivo hasta el
segundo `---` y busca una línea `source: <valor>`. Un archivo sin frontmatter
parseable, o sin línea `source:`, no se considera "owned" y nunca se borra.

### Manejo de errores

- **Abort por umbral:** se registra como error en `stats.errors` (mismo
  mecanismo que errores de render), lo que automáticamente deja el resultado
  de la corrida en `"OK con errores parciales"` vía `RunStats.result`. No se
  toca el filesystem para esa fuente.
- **Falla al borrar un archivo individual** (permisos, etc.): se captura,
  se registra en `stats.errors` y se sigue con los demás candidatos.
- **Archivo con frontmatter no parseable:** se lo trata como no-owned (no se
  borra, no es un error — es el comportamiento esperado para notas ajenas al
  sync).

### `RunStats` y logging

`runlog.py`:
```python
@dataclass
class RunStats:
    seen: int = 0
    created: int = 0
    skipped: int = 0
    deleted: int = 0                                    # nuevo
    deleted_items: list[str] = field(default_factory=list)  # nuevo
    tokens: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    git_ok: bool | None = None
    gbrain_ok: bool | None = None
```

`format_summary` agrega `borrados=N` a la línea de resumen y, debajo, una
línea por nota borrada (mismo estilo que el detalle de errores):

```
[2026-07-11T04:00:00] OK vistos=223 nuevos=2 salteados=219 borrados=2 errores=0 tokens=3480
  - borrado: owner-repo-viejo
  - borrado: owner-otro-repo
```

### `sync.py`: trigger de commit+push+GBrain

El gate pasa de `if stats.created > 0:` a
`if stats.created > 0 or stats.deleted > 0:`. El mensaje de commit refleja
ambos conteos:

```python
f"chore: sync {source.name} (+{stats.created}/-{stats.deleted})"
```

## Testing

`tests/test_pipeline.py`:
- `FakeSource.render` pasa a emitir frontmatter real (`source: Fake`) para
  poder ejercitar el chequeo de ownership.
- Nueva: borra notas de items que ya no están en el fetch actual.
- Nueva: no toca un `.md` sin frontmatter `source:` coincidente (nota ajena).
- Nueva: aborta el borrado (sin tocar archivos, con error en `stats.errors`)
  cuando el ratio de stale supera 50% y hay ≥5 notas owned.
- Nueva: por debajo de `MIN_NOTES_FOR_THRESHOLD`, borra igual aunque el ratio
  sea alto (ej. 1 de 2).
- Nueva: el borrado usa el fetch completo, no se ve acotado por `--limit`.

`tests/test_sync.py`:
- Nueva: una fuente sin items nuevos pero con notas stale dispara igual
  `git_commit_push` (hoy el gate exige `created > 0`).

No se necesitan cambios en `sources/github/source.py` ni
`sources/x/source.py`: ambas ya exponen `name` y sus notas ya incluyen
`source: GitHub` / `source: X` en el frontmatter.

## Criterios de éxito

- Sacarle la estrella a un repo en GitHub, o remover un post de los guardados
  en X, hace que la corrida siguiente de `sync.py` borre la nota
  correspondiente y la commitee/pushee al digital brain.
- Una falla de API que devuelva una lista vacía o muy reducida no borra el
  contenido existente: la corrida queda en "OK con errores parciales" y el
  filesystem no se toca para esa fuente.
- Una nota agregada a mano en `Recursos/Posts` o `Recursos/Repositorios` sin
  el frontmatter `source:` correspondiente nunca se borra por el sync.
- Los tests existentes de creación/skip/límite siguen verdes sin cambios de
  comportamiento.
