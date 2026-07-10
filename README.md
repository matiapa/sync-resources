# sync-resources

Sincroniza recursos externos a notas markdown en el digital brain, de forma
idempotente e incremental. Pensado para correr desde cron. Fuentes soportadas:
repos *starred* de GitHub y posts guardados (*bookmarks*) de X (Twitter).

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # completar OPENAI_API_KEY
```

Requiere `gh` CLI autenticado (`gh auth status`). La reindexación GBrain es
opcional y defensiva: si `gbrain` no está instalado, se omite con un warning.

## Uso

```bash
./venv/bin/python sync.py
```

`sync.py` corre todas las fuentes registradas (GitHub y X). Usá
`--source github` o `--source x` para acotar la corrida a una fuente puntual.
Solo genera notas para items nuevos (los ya presentes en el subdir destino se
saltean). Al generar notas nuevas: commit + push al repo del digital brain y
reindexación GBrain. Si una fuente falla (por ejemplo, X sin autorizar), se
registra el fallo y las demás fuentes siguen corriendo.

## Fuente X (Twitter) — bookmarks

Sincroniza tus posts guardados a `Recursos/Posts/` (configurable con
`X_SUBDIR`). Guarda el texto crudo del tweet, autor, fecha, el tweet citado (si
hay) y las URLs de imágenes/videos; el LLM solo genera la frase `description`
del frontmatter para recall semántico.

### Alta de la app de X (una vez)

1. En el [portal de developers de X](https://developer.x.com/), creá una app
   con OAuth 2.0 habilitado como **confidential client**.
2. Redirect URI (callback): `http://127.0.0.1:8723/callback`.
3. Scopes: `bookmark.read`, `tweet.read`, `users.read`, `offline.access`.
4. Copiá el Client ID y el Client Secret a `.env`
   (`X_CLIENT_ID` / `X_CLIENT_SECRET`).

### Autorización (una vez)

```bash
./venv/bin/python sync.py auth x
```

Abre el navegador para autorizar la app. Al completar, guarda el token en
`.x_token.json` (en esta carpeta, gitignored). El *refresh token* rota solo en
cada corrida, así que no hay que reautorizar: a partir de acá `sync.py`
sincroniza X junto con GitHub. Si el archivo `.x_token.json` se borra o el
refresh se revoca, volvé a correr `sync.py auth x`.

### Corrida de prueba acotada

```bash
./venv/bin/python sync.py --source github --limit 2
```

`--limit N` procesa como máximo N items nuevos por fuente (repos o bookmarks).
Útil para validar la integración con OpenAI con costo mínimo antes de la primera
corrida completa. Como es idempotente, una corrida posterior sin `--limit`
retoma con el resto.

## Cron (ejemplo, diario 4am)

```
0 4 * * * cd /home/matiapa/Applications/sync-resources && ./venv/bin/python sync.py >> sync.log 2>&1
```

## Logfile

Cada corrida agrega una línea de resumen a `sync.log` (fecha, resultado,
métricas, tokens de OpenAI consumidos y detalle de errores). Este archivo queda
en esta carpeta y no se copia al digital brain. Ejemplo:

```
[2026-07-10T04:00:00] OK vistos=223 nuevos=2 salteados=221 errores=0 tokens=3480
```
