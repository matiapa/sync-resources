# Sync de posts guardados de X (Twitter) → digital brain + abstracción de fuentes

**Fecha:** 2026-07-10
**Estado:** Aprobado (diseño)

## Objetivo

Sincronizar los posts *guardados* (bookmarks) de X (Twitter) del usuario a un
conjunto de notas markdown dentro del digital brain
(`/home/matiapa/digital-brain`), para que su asistente de IA personal (que opera
sobre ese vault, tanto por archivos como por búsqueda semántica GBrain) disponga
del contenido de esos posts.

A diferencia de los repos de GitHub —donde el cuerpo de la nota es un **resumen**
del README generado por LLM—, para los posts se guarda el **contenido crudo del
tweet** (texto tal cual, sin resumir), más su fecha y autor. El LLM se usa
únicamente para generar la frase de `description` del frontmatter (recall
semántico). La ejecución es **idempotente e incremental**: solo se generan notas
para posts nuevos. Pensado para correr desde un cronjob del sistema en una
Raspberry Pi (Linux ARM).

Este trabajo también **refactoriza el proyecto hacia una abstracción de
"fuente"** (`Source`), porque hay más fuentes en el roadmap (ej. videos de
YouTube). El sync de repos de GitHub existente se re-expresa como una
implementación de esa abstracción, sin cambiar su comportamiento.

## Alcance

**Incluido:**
- Abstracción `Source` + driver genérico (`pipeline.py`) que maneja el flujo
  común (iterar, saltear ya sincronizados, escribir nota, stats, `--limit`,
  barra de progreso, git+gbrain, logging).
- Nuevo entrypoint único `sync.py` que corre las fuentes registradas
  (`--source x|github` para acotar; sin flag corre todas).
- Fuente **X**: cliente OAuth 2.0 (auth + refresh token), cliente de bookmarks
  (API v2), y render de nota con texto crudo + tweet citado + URLs de media +
  `description` por LLM.
- Refactor de la fuente **GitHub** existente a la nueva forma (mismo
  comportamiento, respaldado por los tests actuales que deben seguir verdes).
- Subcomando `sync.py auth x` para el flujo OAuth inicial (una sola vez).
- Actualización del `CLAUDE.md` del digital brain para el nuevo tipo de nota
  (`source: X`, `subtype: Post`).
- Línea de crontab documentada (no se instala automáticamente).

**Fuera de alcance (iteraciones futuras):**
- Fuente de YouTube (motiva la abstracción, pero se implementa aparte).
- Reconstrucción de hilos completos: solo se guarda el tweet marcado + su
  citado. Se ignoran `retweeted`/`replied_to` en el cuerpo.
- Descarga/rehosting de media: solo se guardan las **URLs** de imágenes/video.
- Actualización de notas ya generadas (los posts no cambian; no aplica).
- Asignación de tags `Area/...` por tema.

## Enfoque

**Abstracción `Source` con driver genérico; idempotencia por filesystem.** Cada
fuente implementa solo lo que le es propio (traer items, ID estable, render de
nota). Un driver común hace el resto. La **fuente de verdad de "ya procesado" es
la existencia del archivo** de nota en la carpeta destino: si existe, se saltea.
Sin state file ni base de datos — el propio vault es el estado.

Alternativas descartadas:
- **Script separado sin abstracción** (un `sync_posts.py` paralelo reusando
  módulos): más simple hoy, pero con YouTube en el roadmap deja duplicación en
  cada orquestador. Descartada por el roadmap concreto de más fuentes.
- **Entrypoint unificado con subcomandos pero sin interfaz `Source`:** acopla el
  `main` a cada fuente; no aísla bien la lógica por fuente.

## Arquitectura

### Interfaz `Source`

```python
@dataclass(frozen=True)
class RenderedNote:
    text: str
    tokens: int = 0        # tokens OpenAI usados al renderizar (0 si no usa LLM)

class Source(Protocol):
    name: str                          # "GitHub", "X" — para logs y commit msg
    subdir: str                        # subcarpeta destino en el brain (de config)
    def fetch(self) -> list[object]: ...          # trae los items de la fuente
    def stem(self, item) -> str: ...              # nombre de archivo sin .md (ID estable)
    def render(self, item) -> RenderedNote: ...   # arma la nota (incl. LLM si aplica)
```

Cada `Source` recibe en su construcción las dependencias compartidas que
necesite (config, cliente OpenAI, `run`/cliente HTTP inyectable), manteniendo el
patrón de inyección de dependencias del código actual para testeo.

### Driver genérico (`pipeline.py`)

```
process_source(cfg, source, limit=None, progress=None) -> RunStats:
    resources_dir = cfg.digital_brain_path / source.subdir
    para cada item de source.fetch():
        si limit y created >= limit: cortar
        seen += 1
        path = resources_dir / (source.stem(item) + ".md")
        si path existe: skipped += 1; continuar
        try:
            note = source.render(item)          # incl. LLM si aplica
            escribir path (solo si render OK); tokens += note.tokens; created += 1
        except Exception as exc:
            errors.append((source.stem(item), str(exc)))   # loguea y sigue
```

Clave: el `stem` (ID) se conoce **antes** de renderizar, así se saltea lo ya
presente sin gastar en llamadas de red ni OpenAI. Nunca se escriben archivos
parciales.

### Estructura de directorios

```
sync.py                 # entrypoint único: corre las fuentes registradas; subcomando auth
pipeline.py             # driver genérico + process_source()
config.py               # config compartida + subdirs/credenciales por fuente
downstream.py           # git + gbrain (sin cambios de comportamiento)
runlog.py               # stats + log (leve cambio: etiqueta por fuente)
sources/
  base.py               # Source (Protocol), RenderedNote
  github/
    client.py           # (ex github_client.py)
    source.py           # GitHubSource: reusa summarizer + render de repo
  x/
    auth.py             # OAuth2 PKCE + refresh token (rotación)
    client.py           # fetch de bookmarks (API v2, paginado, expansiones)
    source.py           # XSource: render texto crudo + citado + media + description LLM
```

`sync_repos.py` se reemplaza por `sync.py`. El `notes.py` y `summarizer.py`
actuales se reutilizan/mueven según convenga al render de GitHub; `summarizer` se
adapta para exponer también una función que devuelve **solo** `description` +
tokens (usada por X).

### Entrypoint y cron

- `./venv/bin/python sync.py` → corre todas las fuentes registradas.
- `--source x` / `--source github` → acota a una fuente.
- `--limit N` → procesa como máximo N items nuevos (por fuente), para corridas de
  prueba acotadas.
- `./venv/bin/python sync.py auth x` → flujo OAuth inicial de X (una sola vez).

El cron pasa a un solo job que corre `sync.py`.

## Autenticación OAuth 2.0 de X

**Setup (una sola vez):** el usuario crea una app en el portal de desarrolladores
de X como **confidential client** (con `client_secret`), con redirect URI
`http://127.0.0.1:8723/callback` (loopback local). `client_id` y `client_secret`
van al `.env` (gitignoreado).

**Scopes:** `bookmark.read tweet.read users.read offline.access`.
- `bookmark.read` → leer los guardados.
- `offline.access` → **imprescindible**: sin este scope X no emite refresh token,
  y el cron desatendido no sería posible.

**Flujo inicial (`sync.py auth x`):**
1. Genera el par PKCE (`code_verifier` / `code_challenge`) y abre en el navegador
   la URL de autorización de X.
2. Levanta un mini servidor HTTP local en el puerto de loopback que captura el
   `code` del redirect (sin copiar/pegar manual).
3. Intercambia `code` → access token + refresh token, y persiste todo en
   `.x_token.json` (gitignoreado):
   ```json
   { "access_token": "...", "refresh_token": "...", "expires_at": "2026-07-10T12:00:00", "user_id": "..." }
   ```

**En cada corrida de cron (fuente X):**
- Carga `.x_token.json`. Si el access token está por vencer (margen ~5 min), usa
  el refresh token para pedir uno nuevo.
- **Rotación de refresh token:** X rota el refresh token en cada uso; se
  **persiste el nuevo** `refresh_token` inmediatamente tras el refresh. De lo
  contrario el próximo cron fallaría.
- El `user_id` (de `GET /2/users/me`) se cachea en el archivo para no re-pedirlo.

Encapsulado en `sources/x/auth.py`, testeable con `run`/cliente HTTP inyectado.

## Cliente de bookmarks (API v2)

`GET /2/users/:id/bookmarks`, **paginado** (sigue `meta.next_token`), con:

- `tweet.fields=created_at,text,author_id,referenced_tweets,attachments`
- `expansions=author_id,referenced_tweets.id,referenced_tweets.id.author_id,attachments.media_keys`
- `user.fields=name,username`
- `media.fields=url,preview_image_url,type,variants`

Resolución de campos:
- **Autor:** `username` (handle) + `name`, vía `includes.users` por `author_id`.
- **Fecha:** `created_at` → `YYYY-MM-DD`.
- **Citado:** `referenced_tweets` con `type == "quoted"` → texto y autor del
  citado desde `includes.tweets` / `includes.users`.
- **Media:** `attachments.media_keys` → `includes.media`. Imágenes usan `url`;
  videos/GIF usan la mejor variante `mp4` de `variants` (por bitrate), con
  fallback a `preview_image_url`.

## Formato de nota (fuente X)

Nombre de archivo: `{tweet_id}.md` (único, estable, idempotente).

```markdown
---
tags:
  - Recursos/Post
type: Recurso
subtype: Post
source: X
description: "<frase de una línea generada por LLM para recall semántico>"
---

# Post de Jane Dev (@janedev)

El texto crudo del tweet marcado, tal cual, sin resumir. Puede tener
varias líneas y saltos.

> **Cita a @otheruser:**
> El texto del tweet citado, también crudo.

## Media
- https://pbs.twimg.com/media/AbCdEf.jpg
- https://video.twimg.com/.../vid.mp4

## Metadatos
- **Autor:** [@janedev](https://x.com/janedev) (Jane Dev)
- **Fecha:** 2026-06-28
- **Post:** https://x.com/janedev/status/1234567890
```

**Reglas de render:**
- **`description`** (frontmatter): la genera el LLM a partir del texto del tweet
  (+ citado si hay). El cuerpo NO se resume — texto crudo. Reusa `summarizer`
  adaptado a devolver solo `description` + tokens. Se escapa como escalar YAML
  seguro (mismo criterio `json.dumps` que las notas de repo, por `:`/comillas).
- **Cita:** el bloque `> **Cita a @...**` aparece solo si hay un `quoted`.
- **Media:** la sección `## Media` aparece solo si hay adjuntos; una URL por
  línea.
- **Fecha:** `YYYY-MM-DD` absoluta (de `created_at`), mismo criterio que en
  repos: la nota se escribe una vez y no se actualiza.
- **Título:** `# Post de {nombre} (@{handle})`.

## Cambios al `CLAUDE.md` del digital brain

Para que el spec de frontmatter quede consistente con el nuevo tipo de nota:

1. **`source`:** agregar `X` al vocabulario cerrado (mantiene la convención de
   capitalización existente).
2. **`subtype`:** documentar el valor `Post` para el campo `subtype` (ya
   admitido como sub-clasificación de `type` desde el trabajo de repos).

## Configuración (`.env`)

Se suman a las variables existentes (`OPENAI_API_KEY`, `OPENAI_MODEL`,
`DIGITAL_BRAIN_PATH`, `GIT_PUSH`, `GBRAIN_SYNC`):

- `GITHUB_SUBDIR` — default `Recursos/Repositorios` (renombre de
  `RESOURCES_SUBDIR`, ahora por-fuente).
- `X_SUBDIR` — default `Recursos/Posts`.
- `X_CLIENT_ID` — obligatoria para la fuente X.
- `X_CLIENT_SECRET` — obligatoria para la fuente X (confidential client).
- `X_TOKEN_PATH` — opcional, default `.x_token.json` junto al script.

Si faltan las credenciales de X, la fuente X se marca con error claro en el
runlog pero **no** rompe las otras fuentes.

## Logging

Se mantiene el logfile de corridas (`sync.log`) append-only en el directorio del
script (gitignored, nunca se copia al brain). Con múltiples fuentes, se escribe
**una línea de resumen por fuente**, etiquetada con el nombre de la fuente:

```
[2026-07-10T04:00:00] X OK vistos=120 nuevos=3 salteados=117 errores=0 tokens=210
[2026-07-10T04:00:05] GitHub OK vistos=223 nuevos=1 salteados=222 errores=0 tokens=1740
```

Cada línea incluye resultado global (OK / OK con errores parciales / FALLO),
métricas (vistos, nuevos, salteados, errores) y tokens OpenAI. Los errores por
item se detallan en líneas siguientes.

## Manejo de errores

- **Falla en un item** (red, API, parseo, LLM): loguea y saltea ese item; no
  aborta la corrida ni la fuente. Se reintenta la próxima vez (no se escribió el
  archivo).
- **Falla de auth de X** (refresh revocado/expirado por inactividad prolongada,
  credenciales faltantes): la fuente X se marca con error y mensaje claro
  ("re-autorizá con `sync.py auth x`"); **las otras fuentes siguen corriendo**.
- **Sin `OPENAI_API_KEY`:** aborta temprano (necesaria para el `description`).
- **`gbrain` ausente o falla:** warning, no fatal.
- **Falla `git push`:** loguea error; las notas quedan escritas localmente y se
  pushean en la próxima corrida.

## Primera corrida

La fuente X procesa **todos** los bookmarks actuales (una llamada a OpenAI por
post, solo para el `description` — barato). Costo puntual único; las corridas
siguientes son incrementales. El endpoint de bookmarks es un *owned read*
(~$0.001 por post) sin mínimo mensual.

## Prerequisitos

- App de X (confidential client) creada, con `client_id`/`client_secret` y
  redirect URI de loopback configurada; flujo `sync.py auth x` corrido una vez.
- `gh` CLI autenticado (para la fuente GitHub, ya está).
- Python 3.11+ y dependencias en el venv (SDK de OpenAI, carga de `.env`,
  cliente HTTP para X, `tqdm`).
- `gbrain` instalado (opcional/defensivo, como hoy).

## Cron

Se entrega el script y una línea de crontab documentada (no se instala
automáticamente). Ejemplo (diario a las 4am):

```
0 4 * * * cd /home/matiapa/Applications/sync-resources && ./venv/bin/python sync.py >> sync.log 2>&1
```

## Criterios de éxito

- `sync.py auth x` completa el flujo OAuth y deja un `.x_token.json` válido con
  refresh token.
- Correr `sync.py` genera una nota bien formada por cada bookmark nuevo, con
  frontmatter válido, texto crudo del tweet, tweet citado (si hay), URLs de media
  (si hay), autor y fecha; y una nota por cada repo faveado nuevo (comportamiento
  de GitHub intacto).
- Una segunda corrida sin items nuevos no genera cambios (idempotente) y no hace
  commit.
- El refresh token rota y se persiste correctamente entre corridas (el cron sigue
  funcionando sin re-autorización manual).
- Un fallo de auth en X no impide que la fuente GitHub sincronice.
- Los tests existentes de la fuente GitHub siguen verdes tras el refactor.
