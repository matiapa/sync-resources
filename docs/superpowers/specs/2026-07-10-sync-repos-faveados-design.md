# Sync de repos faveados de GitHub → digital brain

**Fecha:** 2026-07-10
**Estado:** Aprobado (diseño)

## Objetivo

Sincronizar los repos *starred* (faveados) de GitHub del usuario (`matiapa`) a
un conjunto de notas markdown dentro del digital brain
(`/home/matiapa/digital-brain`), para que su asistente de IA personal (que opera
sobre ese vault, tanto por archivos como por búsqueda semántica GBrain) disponga
de la información de esos repos.

Una nota markdown por repo, con un resumen del README, autor, estrellas y link.
La ejecución es **idempotente e incremental**: solo se generan notas para repos
nuevos; los ya procesados no se re-sincronizan aunque cambie su README. Pensado
para correr desde un cronjob del sistema en una Raspberry Pi (Linux ARM).

## Alcance

**Incluido:**
- Script Python único que trae los repos faveados, genera una nota por repo
  nuevo, commitea+pushea al repo del digital brain y reindexa en GBrain.
- Actualización del `CLAUDE.md` del digital brain para reflejar el nuevo formato
  de nota.
- Línea de crontab documentada (no se instala automáticamente).

**Fuera de alcance (iteraciones futuras):**
- Asignación de tags `Area/...` por tema del repo. Se difiere hasta tener un
  vocabulario de áreas armado vía clustering no supervisado sobre las notas ya
  sincronizadas.
- Actualización de notas de repos ya procesados ante cambios en el README.
- Instalación/configuración de `gbrain` en la Pi (prerequisito documentado, ver
  abajo).

## Enfoque

**Script Python único, idempotencia por filesystem.** Un solo archivo `.py`
organizado en funciones con responsabilidad clara (cliente GitHub, resumidor
OpenAI, escritor de notas, git + sync). La **fuente de verdad de "ya procesado"
es la existencia del archivo** `owner-repo.md` en la carpeta destino: si existe,
se saltea. Sin state file ni base de datos — el propio vault es el estado. Esto
evita drift entre un estado externo y los archivos reales.

Alternativas descartadas: state file JSON (agrega un archivo a mantener
sincronizado, con riesgo de desfase); consultar git/gbrain para deducir
existentes (sobre-ingeniería).

## Componentes y flujo

Una corrida del script ejecuta:

1. **Cargar configuración** desde `.env` en el directorio del script.
2. **Traer repos faveados:** `gh api user/starred --paginate` (usa la auth ya
   configurada de `gh`, sin gestión de tokens propia). Devuelve, por repo:
   `full_name` (owner/repo), `owner.login`, `html_url`, `stargazers_count`,
   `description`.
3. **Filtrar nuevos:** para cada repo, derivar el filename
   `{owner}-{repo}.md` (el `/` de `full_name` se reemplaza por `-`; `full_name`
   es único en GitHub, así que no hay colisiones). Si el archivo **ya existe** en
   `{DIGITAL_BRAIN_PATH}/{RESOURCES_SUBDIR}/` → saltear.
4. **Generar nota (solo repos nuevos):**
   - Traer README: `gh api repos/{owner}/{repo}/readme` (contenido en base64, se
     decodifica). Si el repo no tiene README → usar la `description` del repo
     como fallback; si tampoco hay description → resumen mínimo con el nombre.
   - Resumir con OpenAI (modelo configurable, default `gpt-5.5`). La llamada
     devuelve salida estructurada con dos campos:
     - `summary`: párrafo que describe qué hace el repo (cuerpo de la nota).
     - `description`: resumen de una frase (campo `description` del frontmatter,
       para recall semántico).
5. **Escribir la nota** en `{RESOURCES_SUBDIR}/{owner}-{repo}.md`, **solo si
   todo el paso 4 salió bien**. Nunca se escriben archivos parciales: si falla el
   README, la API o el parseo, se saltea ese repo y se reintenta en la próxima
   corrida.
6. **Downstream (solo si se generó al menos una nota nueva):**
   - `git add {RESOURCES_SUBDIR}` + `git commit` + `git push` en
     `DIGITAL_BRAIN_PATH` (branch `main`, remote `origin` →
     `https://github.com/matiapa/digital-brain`). Toggle `GIT_PUSH`.
   - Reindexar en GBrain (`gbrain import`/sync). Toggle `GBRAIN_SYNC`. **Llamada
     defensiva:** si `gbrain` no está en el PATH, loguea warning y no falla la
     corrida.
7. **Logging** a un archivo en el directorio del script, para diagnóstico del
   cron.

## Formato de nota

Respeta el spec de frontmatter de `Notas/` del `CLAUDE.md`, con las extensiones
descritas más abajo.

```markdown
---
tags:
  - Recursos/Repositorio
type: Recurso
subtype: Repositorio
source: GitHub
description: <resumen de una frase del repo>
---

# owner/repo

<párrafo resumen del README generado con OpenAI>

## Metadatos
- **Autor:** [owner](https://github.com/owner)
- **Estrellas:** 1234
- **Repo:** https://github.com/owner/repo
```

- Autor, estrellas y link van en el **cuerpo**, no en frontmatter.
- El título `# owner/repo` usa el `full_name` del repo.

## Cambios al `CLAUDE.md` del digital brain

Para que el spec de frontmatter quede consistente con el nuevo tipo de nota:

1. **`type`:** agregar `Recurso` al vocabulario cerrado.
2. **`source`:** agregar `GitHub` al vocabulario cerrado (se mantiene la
   convención de capitalización existente: `Keep`, `Notion`, `YouTube`).
3. **Nuevo campo `subtype`:** documentar el campo `subtype` (scalar) con el
   valor `Repositorio`. **Enmienda necesaria:** la regla actual dice *"No crear
   campos ad-hoc que dupliquen esta función — cualquier clasificación adicional
   es un tag más, nunca un campo nuevo"*. Hay que ajustar esa regla para
   admitir `subtype` como sub-clasificación válida dentro de `type`.

## Configuración (`.env`)

Archivo `.env` en el directorio del script (gitignored). Variables:

- `OPENAI_API_KEY` — obligatoria. Si falta, el script aborta temprano con
  mensaje claro.
- `OPENAI_MODEL` — default `gpt-5.5`.
- `DIGITAL_BRAIN_PATH` — default `/home/matiapa/digital-brain`.
- `RESOURCES_SUBDIR` — default `Recursos externos`.
- `GIT_PUSH` — toggle (default on).
- `GBRAIN_SYNC` — toggle (default on).

## Manejo de errores

- **Falla en un repo** (README, API, red, parseo OpenAI): loguea y saltea ese
  repo; no aborta la corrida. Se reintenta la próxima vez porque no se escribió
  el archivo.
- **Sin `OPENAI_API_KEY`:** aborta temprano.
- **`gbrain` ausente o falla el sync:** warning, no fatal (las notas ya quedaron
  escritas y commiteadas).
- **Falla `git push`** (ej. sin red): loguea error; las notas quedan escritas
  localmente y el commit se pushea en la próxima corrida.

## Primera corrida

Procesa **todos** los repos actualmente faveados (una llamada a OpenAI por
repo). Es un costo puntual único; las corridas siguientes son incrementales
(solo repos nuevos desde la última vez).

## Prerequisitos

- `gh` CLI autenticado (ya lo está en la Pi, usuario `matiapa`, scope `repo`).
- Python 3.11+ (disponible).
- Dependencias Python: SDK de OpenAI (+ carga de `.env`). En un venv.
- **`gbrain` instalado y configurado en la Pi** — prerequisito para el paso de
  reindexación. Mientras no esté, el script funciona igual (warning defensivo) y
  la reindexación la puede hacer otra máquina tras el `git pull`.

## Cron

Se entrega el script y una línea de crontab **documentada** (no se instala
automáticamente); el usuario controla el schedule. Ejemplo (diario a las 4am):

```
0 4 * * * cd /home/matiapa/Applications/sync-resources && ./venv/bin/python sync_repos.py >> sync.log 2>&1
```

## Criterios de éxito

- Correr el script genera una nota bien formada por cada repo faveado nuevo, con
  frontmatter válido según el spec extendido, resumen del README, autor,
  estrellas y link.
- Una segunda corrida sin repos nuevos no genera cambios (idempotente) y no
  hace commit.
- Los repos ya procesados no se tocan aunque cambie su README.
- Tras generar notas nuevas, quedan commiteadas y pusheadas al repo del digital
  brain, y (si `gbrain` está disponible) reindexadas en GBrain.
