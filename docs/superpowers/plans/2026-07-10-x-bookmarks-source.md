# Fuente X (bookmarks) sobre la abstracción `Source` (Plan 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar una fuente X que sincroniza los posts guardados (bookmarks) del usuario a notas markdown, con el texto crudo del tweet + tweet citado + URLs de media, y una `description` de una línea generada por LLM para el frontmatter.

**Architecture:** Sobre la abstracción `Source` (Plan 1, ya en `main`/`master`), se agrega el paquete `sources/x/` con: OAuth 2.0 PKCE + refresh token (`auth.py`), cliente de bookmarks API v2 con expansiones y paginación (`client.py`), modelo `Tweet` (`models.py`), render de nota (`notes.py`) y `XSource` (`source.py`). `sync.py` registra la fuente y expone un subcomando `auth x` para el flujo OAuth inicial. Toda la lógica de red se aísla detrás de callables inyectables para poder testear sin credenciales ni red.

**Tech Stack:** Python 3.11+, pytest, OpenAI SDK, `requests` (nuevo), tqdm, python-dotenv.

## Global Constraints

- Python 3.11+.
- **Inyección de dependencias:** toda función que toque red recibe el callable HTTP (`post`/`get`) o el reloj (`now`) como parámetro con default real, para testear sin red. Igual patrón que `run=subprocess.run` en el código existente.
- **TDD estricto:** test que falla → implementación mínima → test verde → commit.
- **No romper la fuente GitHub ni sus tests:** los 42 tests actuales siguen verdes.
- **Sin resumir el cuerpo:** el cuerpo de la nota es el texto crudo del tweet; el LLM solo genera la `description` de una línea del frontmatter.
- **Escapado YAML seguro** de la `description` con `json.dumps(value, ensure_ascii=False)` (mismo criterio que `notes._yaml_scalar`).
- Barra de progreso tqdm con `disable=None`.
- **Hosts de X:** autorización `https://x.com/i/oauth2/authorize`; token `https://api.x.com/2/oauth2/token`; API `https://api.x.com/2`. Cliente **confidential** (Basic auth `client_id:client_secret` en el endpoint de token).
- **Scopes OAuth:** `bookmark.read tweet.read users.read offline.access`.
- **Credenciales:** `X_CLIENT_ID`/`X_CLIENT_SECRET` pueden faltar; si faltan, la fuente X falla con mensaje claro y **no** rompe las otras fuentes. Los pasos que requieren credenciales reales (flujo `auth x` interactivo y smoke e2e) se marcan como verificación diferida hasta que el usuario provea la app de X.
- Todo commit termina con:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

## File Structure (estado final del Plan 2)

```
config.py               # MODIF: x_client_id, x_client_secret, x_subdir, x_token_path
summarizer.py           # MODIF: + describe() (una frase, sin summary)
sync.py                 # MODIF: registra XSource; subcomando `auth x`; --source x
requirements.txt        # MODIF: + requests
.gitignore              # MODIF: + .x_token.json
sources/
  x/
    __init__.py         # NUEVO
    models.py           # NUEVO: Tweet, QuotedTweet
    auth.py             # NUEVO: PKCE, exchange, refresh, TokenStore, get_valid_access_token
    client.py           # NUEVO: get_user_id, get_bookmarks, parse_bookmarks
    notes.py            # NUEVO: render_post_note
    source.py           # NUEVO: XSource
tests/
  sources/
    x/
      __init__.py       # NUEVO
      test_models.py    # NUEVO
      test_auth.py      # NUEVO
      test_client.py    # NUEVO
      test_notes.py     # NUEVO
      test_source.py    # NUEVO
  test_summarizer.py    # MODIF: + test de describe()
  test_config.py        # MODIF: + defaults de X
  test_sync.py          # MODIF: + XSource registrada / auth subcommand
```

Nota: el cambio al `CLAUDE.md` del digital brain (agregar `source: X`, `subtype: Post`) es en **otro repo** (el vault). Se documenta como paso manual en Task 9; no es código de este repo.

---

### Task 1: Config de X + `.gitignore`

**Files:**
- Modify: `config.py`
- Modify: `.gitignore`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` gana campos `x_client_id: str | None`, `x_client_secret: str | None`, `x_subdir: str`, `x_token_path: Path`. `load_config` lee `X_CLIENT_ID`, `X_CLIENT_SECRET` (default `None`), `X_SUBDIR` (default `"Recursos/Posts"`), `X_TOKEN_PATH` (default `script_dir / ".x_token.json"`).

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_config.py`:
```python
def test_x_defaults():
    cfg = load_config(env={"OPENAI_API_KEY": "k"}, script_dir=Path("/scripts"))
    assert cfg.x_client_id is None
    assert cfg.x_client_secret is None
    assert cfg.x_subdir == "Recursos/Posts"
    assert cfg.x_token_path == Path("/scripts/.x_token.json")


def test_x_from_env():
    cfg = load_config(
        env={"OPENAI_API_KEY": "k", "X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "sec",
             "X_SUBDIR": "Recursos/Tweets", "X_TOKEN_PATH": "/tmp/tok.json"},
        script_dir=Path("/s"),
    )
    assert cfg.x_client_id == "cid"
    assert cfg.x_client_secret == "sec"
    assert cfg.x_subdir == "Recursos/Tweets"
    assert cfg.x_token_path == Path("/tmp/tok.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL (`TypeError`: `Config` no acepta `x_client_id`).

- [ ] **Step 3: Implement**

En `config.py`, agregar al dataclass `Config` (después de `github_subdir`):
```python
    x_client_id: str | None
    x_client_secret: str | None
    x_subdir: str
    x_token_path: Path
```
En `load_config`, dentro del `return Config(...)`, agregar (después de `github_subdir=...`):
```python
        x_client_id=env.get("X_CLIENT_ID"),
        x_client_secret=env.get("X_CLIENT_SECRET"),
        x_subdir=env.get("X_SUBDIR", "Recursos/Posts"),
        x_token_path=Path(env["X_TOKEN_PATH"]) if env.get("X_TOKEN_PATH") else script_dir / ".x_token.json",
```

En `.gitignore`, agregar una línea:
```
.x_token.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (todos verdes).

- [ ] **Step 5: Commit**

```bash
git add config.py .gitignore tests/test_config.py
git commit -m "feat: add X source config fields and token gitignore

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Modelo `Tweet`

**Files:**
- Create: `sources/x/__init__.py`
- Create: `sources/x/models.py`
- Create: `tests/sources/x/__init__.py`
- Test: `tests/sources/x/test_models.py`

**Interfaces:**
- Produces:
  - `QuotedTweet(author_username: str, text: str)` — frozen dataclass.
  - `Tweet(id: str, text: str, author_username: str, author_name: str, created_at: str, quoted: QuotedTweet | None = None, media_urls: tuple[str, ...] = ())` — frozen dataclass.
    - `created_at` es el string ISO8601 crudo de la API (ej. `"2026-06-28T14:00:00.000Z"`).

- [ ] **Step 1: Write the failing test**

`tests/sources/x/__init__.py` → vacío.

`tests/sources/x/test_models.py`:
```python
from sources.x.models import Tweet, QuotedTweet


def test_tweet_minimal_defaults():
    t = Tweet(id="1", text="hola", author_username="jane",
              author_name="Jane", created_at="2026-06-28T14:00:00.000Z")
    assert t.quoted is None
    assert t.media_urls == ()


def test_tweet_with_quote_and_media():
    q = QuotedTweet(author_username="other", text="citado")
    t = Tweet(id="2", text="mira esto", author_username="jane", author_name="Jane",
              created_at="2026-06-28T14:00:00.000Z", quoted=q,
              media_urls=("https://pbs.twimg.com/a.jpg",))
    assert t.quoted.author_username == "other"
    assert t.media_urls == ("https://pbs.twimg.com/a.jpg",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/x/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sources.x'`).

- [ ] **Step 3: Implement**

`sources/x/__init__.py` → vacío.

`sources/x/models.py`:
```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuotedTweet:
    author_username: str
    text: str


@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    author_username: str
    author_name: str
    created_at: str                       # ISO8601 crudo de la API
    quoted: QuotedTweet | None = None
    media_urls: tuple[str, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/x/test_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/x/__init__.py sources/x/models.py tests/sources/x/__init__.py tests/sources/x/test_models.py
git commit -m "feat: add Tweet model for X source

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: OAuth PKCE + intercambio/refresh de tokens

**Files:**
- Create: `sources/x/auth.py`
- Test: `tests/sources/x/test_auth.py`

**Interfaces:**
- Consumes: `requests` (inyectado como `post`).
- Produces:
  - `generate_pkce() -> tuple[str, str]` — `(code_verifier, code_challenge)`; challenge = base64url(sha256(verifier)) sin padding.
  - `AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"`, `TOKEN_URL = "https://api.x.com/2/oauth2/token"`, `SCOPES = "bookmark.read tweet.read users.read offline.access"`.
  - `build_authorize_url(client_id, redirect_uri, code_challenge, state) -> str`.
  - `exchange_code(client_id, client_secret, code, code_verifier, redirect_uri, *, post=requests.post) -> dict` — POST con Basic auth; devuelve el JSON del token (`access_token`, `refresh_token`, `expires_in`, ...).
  - `refresh_access_token(client_id, client_secret, refresh_token, *, post=requests.post) -> dict`.
  - `AuthError(Exception)` — se levanta si la respuesta HTTP no es 2xx.

- [ ] **Step 1: Write the failing test**

`tests/sources/x/test_auth.py`:
```python
import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from sources.x import auth


def test_generate_pkce_challenge_matches_verifier():
    verifier, challenge = auth.generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert challenge == expected


def test_build_authorize_url_has_required_params():
    url = auth.build_authorize_url("cid", "http://127.0.0.1:8723/callback", "chal", "st")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8723/callback"]
    assert q["code_challenge"] == ["chal"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["st"]
    assert q["scope"] == [auth.SCOPES]


def _resp(json_body, status=200):
    return SimpleNamespace(
        status_code=status, json=lambda: json_body,
        text=str(json_body), ok=(200 <= status < 300),
    )


def test_exchange_code_posts_with_basic_auth():
    calls = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        calls["url"] = url
        calls["data"] = data
        calls["auth"] = auth
        return _resp({"access_token": "at", "refresh_token": "rt", "expires_in": 7200})

    body = auth.exchange_code("cid", "sec", "the-code", "verifier",
                              "http://127.0.0.1:8723/callback", post=fake_post)
    assert body["access_token"] == "at"
    assert calls["url"] == auth.TOKEN_URL
    assert calls["auth"] == ("cid", "sec")
    assert calls["data"]["grant_type"] == "authorization_code"
    assert calls["data"]["code"] == "the-code"
    assert calls["data"]["code_verifier"] == "verifier"
    assert calls["data"]["redirect_uri"] == "http://127.0.0.1:8723/callback"


def test_refresh_access_token_uses_refresh_grant():
    seen = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        seen["data"] = data
        return _resp({"access_token": "new", "refresh_token": "rot", "expires_in": 7200})

    body = auth.refresh_access_token("cid", "sec", "old-rt", post=fake_post)
    assert body["access_token"] == "new"
    assert seen["data"]["grant_type"] == "refresh_token"
    assert seen["data"]["refresh_token"] == "old-rt"


def test_exchange_code_raises_on_error():
    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        return _resp({"error": "invalid_grant"}, status=400)

    with pytest.raises(auth.AuthError):
        auth.exchange_code("cid", "sec", "bad", "v", "http://127.0.0.1:8723/callback", post=fake_post)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/x/test_auth.py -v`
Expected: FAIL (`ModuleNotFoundError` o `requests` no instalado — instalar en Task 3 Step 3).

- [ ] **Step 3: Implement**

Instalar `requests` y agregarlo a `requirements.txt`:
```bash
./venv/bin/pip install "requests>=2.31"
```
En `requirements.txt`, agregar la línea `requests>=2.31`.

`sources/x/auth.py`:
```python
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = "bookmark.read tweet.read users.read offline.access"

_TIMEOUT = 30


class AuthError(Exception):
    pass


def generate_pkce() -> tuple[str, str]:
    """Genera (code_verifier, code_challenge) para OAuth 2.0 PKCE (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, code_challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(data: dict, client_id: str, client_secret: str, post) -> dict:
    resp = post(
        TOKEN_URL,
        data=data,
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    if not getattr(resp, "ok", 200 <= resp.status_code < 300):
        raise AuthError(f"Token endpoint devolvió {resp.status_code}: {resp.text}")
    return resp.json()


def exchange_code(client_id, client_secret, code, code_verifier, redirect_uri, *, post=requests.post) -> dict:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        client_id, client_secret, post,
    )


def refresh_access_token(client_id, client_secret, refresh_token, *, post=requests.post) -> dict:
    return _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        client_id, client_secret, post,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/x/test_auth.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/x/auth.py tests/sources/x/test_auth.py requirements.txt
git commit -m "feat: add X OAuth PKCE and token exchange/refresh

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `TokenStore` + `get_valid_access_token` (con rotación)

**Files:**
- Modify: `sources/x/auth.py`
- Test: `tests/sources/x/test_auth.py` (agregar casos)

**Interfaces:**
- Consumes: `exchange_code`/`refresh_access_token` (Task 3).
- Produces:
  - `TokenStore(path: Path)` con:
    - `load() -> dict` — lee el JSON; si no existe, `{}`.
    - `save(data: dict) -> None` — escribe el JSON (indentado, `ensure_ascii=False`).
  - `save_token_response(store, body, user_id=None, now=datetime.now) -> dict` — normaliza el token response a `{access_token, refresh_token, expires_at (ISO), user_id}` y lo persiste; conserva `user_id` previo si no se pasa uno nuevo.
  - `get_valid_access_token(store, client_id, client_secret, *, now=datetime.now, post=requests.post, skew_seconds=300) -> str` — carga el token; si `expires_at` está a menos de `skew_seconds` de vencer (o no hay), refresca con el `refresh_token`, **persiste el nuevo `refresh_token` rotado** y devuelve el `access_token` vigente. Levanta `AuthError` si no hay `refresh_token` guardado (mensaje: "re-autorizá con `sync.py auth x`").

- [ ] **Step 1: Write the failing test**

Agregar a `tests/sources/x/test_auth.py`:
```python
import json
from datetime import datetime, timedelta
from pathlib import Path

from sources.x.auth import TokenStore, save_token_response, get_valid_access_token, AuthError


def _store(tmp_path) -> TokenStore:
    return TokenStore(tmp_path / ".x_token.json")


def test_store_load_missing_returns_empty(tmp_path):
    assert _store(tmp_path).load() == {}


def test_save_token_response_normalizes_and_persists(tmp_path):
    store = _store(tmp_path)
    now = datetime(2026, 7, 10, 12, 0, 0)
    data = save_token_response(store,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 7200},
        user_id="u1", now=lambda: now)
    assert data["access_token"] == "at"
    assert data["refresh_token"] == "rt"
    assert data["user_id"] == "u1"
    assert data["expires_at"] == (now + timedelta(seconds=7200)).isoformat()
    # persistido en disco
    assert json.loads(Path(store.path).read_text())["access_token"] == "at"


def test_get_valid_access_token_returns_current_when_fresh(tmp_path):
    store = _store(tmp_path)
    future = (datetime(2026, 7, 10, 12, 0, 0) + timedelta(hours=1)).isoformat()
    store.save({"access_token": "fresh", "refresh_token": "rt", "expires_at": future, "user_id": "u1"})

    def fail_post(*a, **k):
        raise AssertionError("no debería refrescar")

    tok = get_valid_access_token(store, "cid", "sec",
        now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=fail_post)
    assert tok == "fresh"


def test_get_valid_access_token_refreshes_and_rotates(tmp_path):
    store = _store(tmp_path)
    past = (datetime(2026, 7, 10, 12, 0, 0) - timedelta(minutes=1)).isoformat()
    store.save({"access_token": "old", "refresh_token": "old-rt", "expires_at": past, "user_id": "u1"})

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        from types import SimpleNamespace
        return SimpleNamespace(status_code=200, ok=True, text="",
            json=lambda: {"access_token": "new", "refresh_token": "new-rt", "expires_in": 7200})

    tok = get_valid_access_token(store, "cid", "sec",
        now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=fake_post)
    assert tok == "new"
    saved = store.load()
    assert saved["refresh_token"] == "new-rt"   # rotación persistida
    assert saved["user_id"] == "u1"             # user_id conservado


def test_get_valid_access_token_without_refresh_token_raises(tmp_path):
    store = _store(tmp_path)  # vacío
    with pytest.raises(AuthError):
        get_valid_access_token(store, "cid", "sec",
            now=lambda: datetime(2026, 7, 10, 12, 0, 0), post=lambda *a, **k: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/x/test_auth.py -v`
Expected: FAIL (`ImportError: cannot import name 'TokenStore'`).

- [ ] **Step 3: Implement**

Agregar a `sources/x/auth.py` (imports arriba: `import json`, `from datetime import datetime, timedelta`, `from pathlib import Path`):
```python
class TokenStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def save_token_response(store: TokenStore, body: dict, user_id: str | None = None,
                        now=datetime.now) -> dict:
    prev = store.load()
    expires_at = (now() + timedelta(seconds=int(body.get("expires_in", 7200)))).isoformat()
    data = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", prev.get("refresh_token")),
        "expires_at": expires_at,
        "user_id": user_id if user_id is not None else prev.get("user_id"),
    }
    store.save(data)
    return data


def get_valid_access_token(store: TokenStore, client_id: str, client_secret: str, *,
                           now=datetime.now, post=requests.post, skew_seconds: int = 300) -> str:
    data = store.load()
    expires_at = data.get("expires_at")
    if data.get("access_token") and expires_at:
        remaining = datetime.fromisoformat(expires_at) - now()
        if remaining.total_seconds() > skew_seconds:
            return data["access_token"]
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise AuthError("No hay refresh token guardado. Re-autorizá con `sync.py auth x`.")
    body = refresh_access_token(client_id, client_secret, refresh_token, post=post)
    data = save_token_response(store, body, user_id=data.get("user_id"), now=now)
    return data["access_token"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/x/test_auth.py -v`
Expected: PASS (10 passed en total en el archivo).

- [ ] **Step 5: Commit**

```bash
git add sources/x/auth.py tests/sources/x/test_auth.py
git commit -m "feat: add X token store with refresh-token rotation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Cliente de bookmarks + parser

**Files:**
- Create: `sources/x/client.py`
- Test: `tests/sources/x/test_client.py`

**Interfaces:**
- Consumes: `requests` (inyectado como `get`); `sources.x.models.Tweet/QuotedTweet`.
- Produces:
  - `API_BASE = "https://api.x.com/2"`.
  - `get_user_id(access_token, *, get=requests.get) -> str` — `GET /users/me`, devuelve `data.id`.
  - `get_bookmarks(user_id, access_token, *, get=requests.get) -> list[Tweet]` — pagina `GET /users/:id/bookmarks` (sigue `meta.next_token`), concatena `parse_bookmarks` de cada página.
  - `parse_bookmarks(payload: dict) -> list[Tweet]` — función pura que arma `Tweet`s desde una página (con `includes.users`, `includes.tweets`, `includes.media`). Un `referenced_tweets` con `type == "quoted"` → `QuotedTweet`. Media: imágenes usan `url`; `video`/`animated_gif` usan la mejor variante mp4 (`variants` por `bit_rate`), fallback `preview_image_url`.
  - `BOOKMARK_FIELDS` (dict de query params con `tweet.fields`, `expansions`, `user.fields`, `media.fields`) según el spec.

- [ ] **Step 1: Write the failing test**

`tests/sources/x/test_client.py`:
```python
from types import SimpleNamespace

from sources.x import client
from sources.x.models import Tweet, QuotedTweet


def _resp(json_body, status=200):
    return SimpleNamespace(status_code=status, ok=(200 <= status < 300),
                           text=str(json_body), json=lambda: json_body)


PAGE = {
    "data": [
        {
            "id": "100", "text": "un tweet con imagen", "author_id": "u1",
            "created_at": "2026-06-28T14:00:00.000Z",
            "attachments": {"media_keys": ["m1"]},
        },
        {
            "id": "200", "text": "cito a alguien", "author_id": "u1",
            "created_at": "2026-06-29T10:00:00.000Z",
            "referenced_tweets": [{"type": "quoted", "id": "999"}],
        },
    ],
    "includes": {
        "users": [
            {"id": "u1", "username": "jane", "name": "Jane Dev"},
            {"id": "u2", "username": "other", "name": "Other"},
        ],
        "tweets": [{"id": "999", "author_id": "u2", "text": "texto citado"}],
        "media": [{"media_key": "m1", "type": "photo", "url": "https://pbs.twimg.com/a.jpg"}],
    },
    "meta": {},
}


def test_parse_bookmarks_builds_tweets_with_media_and_quote():
    tweets = client.parse_bookmarks(PAGE)
    assert tweets[0] == Tweet(
        id="100", text="un tweet con imagen", author_username="jane",
        author_name="Jane Dev", created_at="2026-06-28T14:00:00.000Z",
        media_urls=("https://pbs.twimg.com/a.jpg",),
    )
    assert tweets[1].quoted == QuotedTweet(author_username="other", text="texto citado")


def test_parse_bookmarks_video_uses_best_mp4_variant():
    page = {
        "data": [{"id": "1", "text": "vid", "author_id": "u1",
                  "created_at": "2026-06-28T14:00:00.000Z",
                  "attachments": {"media_keys": ["v1"]}}],
        "includes": {
            "users": [{"id": "u1", "username": "jane", "name": "Jane"}],
            "media": [{"media_key": "v1", "type": "video",
                       "variants": [
                           {"bit_rate": 256000, "content_type": "video/mp4", "url": "low.mp4"},
                           {"bit_rate": 832000, "content_type": "video/mp4", "url": "high.mp4"},
                           {"content_type": "application/x-mpegURL", "url": "stream.m3u8"},
                       ]}],
        },
        "meta": {},
    }
    tweets = client.parse_bookmarks(page)
    assert tweets[0].media_urls == ("high.mp4",)


def test_get_user_id():
    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.endswith("/users/me")
        return _resp({"data": {"id": "u1", "username": "jane", "name": "Jane"}})

    assert client.get_user_id("token", get=fake_get) == "u1"


def test_get_bookmarks_follows_pagination():
    pages = [
        {"data": [{"id": "1", "text": "a", "author_id": "u1",
                   "created_at": "2026-06-28T14:00:00.000Z"}],
         "includes": {"users": [{"id": "u1", "username": "j", "name": "J"}]},
         "meta": {"next_token": "TOK"}},
        {"data": [{"id": "2", "text": "b", "author_id": "u1",
                   "created_at": "2026-06-29T14:00:00.000Z"}],
         "includes": {"users": [{"id": "u1", "username": "j", "name": "J"}]},
         "meta": {}},
    ]
    seen_tokens = []

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_tokens.append(params.get("pagination_token"))
        return _resp(pages.pop(0))

    tweets = client.get_bookmarks("u1", "token", get=fake_get)
    assert [t.id for t in tweets] == ["1", "2"]
    assert seen_tokens == [None, "TOK"]   # 1ra sin token, 2da con next_token
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/x/test_client.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sources.x.client'`).

- [ ] **Step 3: Implement**

`sources/x/client.py`:
```python
import requests

from sources.x.models import QuotedTweet, Tweet

API_BASE = "https://api.x.com/2"
_TIMEOUT = 30

BOOKMARK_FIELDS = {
    "tweet.fields": "created_at,text,author_id,referenced_tweets,attachments",
    "expansions": "author_id,referenced_tweets.id,referenced_tweets.id.author_id,attachments.media_keys",
    "user.fields": "name,username",
    "media.fields": "url,preview_image_url,type,variants",
    "max_results": "100",
}


class XApiError(Exception):
    pass


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _check(resp):
    if not getattr(resp, "ok", 200 <= resp.status_code < 300):
        raise XApiError(f"X API devolvió {resp.status_code}: {resp.text}")
    return resp.json()


def get_user_id(access_token: str, *, get=requests.get) -> str:
    resp = get(f"{API_BASE}/users/me", headers=_auth_headers(access_token), params=None, timeout=_TIMEOUT)
    return _check(resp)["data"]["id"]


def _best_media_url(media: dict) -> str | None:
    if media.get("type") == "photo":
        return media.get("url")
    variants = [v for v in media.get("variants", []) if v.get("content_type") == "video/mp4"]
    if variants:
        best = max(variants, key=lambda v: v.get("bit_rate", 0))
        return best.get("url")
    return media.get("preview_image_url")


def parse_bookmarks(payload: dict) -> list[Tweet]:
    includes = payload.get("includes", {})
    users = {u["id"]: u for u in includes.get("users", [])}
    tweets_by_id = {t["id"]: t for t in includes.get("tweets", [])}
    media_by_key = {m["media_key"]: m for m in includes.get("media", [])}

    result: list[Tweet] = []
    for item in payload.get("data", []):
        author = users.get(item.get("author_id"), {})
        quoted = None
        for ref in item.get("referenced_tweets", []):
            if ref.get("type") == "quoted":
                qt = tweets_by_id.get(ref.get("id"))
                if qt:
                    qa = users.get(qt.get("author_id"), {})
                    quoted = QuotedTweet(author_username=qa.get("username", ""), text=qt.get("text", ""))
                break
        media_urls = []
        for key in item.get("attachments", {}).get("media_keys", []):
            media = media_by_key.get(key)
            if media:
                url = _best_media_url(media)
                if url:
                    media_urls.append(url)
        result.append(Tweet(
            id=item["id"], text=item.get("text", ""),
            author_username=author.get("username", ""), author_name=author.get("name", ""),
            created_at=item.get("created_at", ""), quoted=quoted,
            media_urls=tuple(media_urls),
        ))
    return result


def get_bookmarks(user_id: str, access_token: str, *, get=requests.get) -> list[Tweet]:
    tweets: list[Tweet] = []
    next_token = None
    while True:
        params = dict(BOOKMARK_FIELDS)
        if next_token:
            params["pagination_token"] = next_token
        else:
            params["pagination_token"] = None
        resp = get(f"{API_BASE}/users/{user_id}/bookmarks",
                   headers=_auth_headers(access_token), params=params, timeout=_TIMEOUT)
        payload = _check(resp)
        tweets.extend(parse_bookmarks(payload))
        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
    return tweets
```

Nota: `params["pagination_token"] = None` en la primera página se incluye para que el test lo observe; `requests` omite params con valor `None`, así que no se envía a la API.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/x/test_client.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/x/client.py tests/sources/x/test_client.py
git commit -m "feat: add X bookmarks client with pagination and parsing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `describe()` en summarizer + render de nota de post

**Files:**
- Modify: `summarizer.py`
- Create: `sources/x/notes.py`
- Modify: `tests/test_summarizer.py`
- Test: `tests/sources/x/test_notes.py`

**Interfaces:**
- Produces:
  - `summarizer.describe(text: str, model: str, client) -> tuple[str, int]` — pide al LLM una sola frase (para `description`); devuelve `(frase, tokens)`.
  - `sources.x.notes.render_post_note(tweet: Tweet, description: str) -> str` — arma el markdown del post.

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/test_summarizer.py`:
```python
def test_describe_returns_sentence_and_tokens():
    class FakeResp:
        class choices0:
            class message:
                content = '{"description": "Una frase corta."}'
        choices = [choices0]
        usage = type("U", (), {"total_tokens": 12})()

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeResp()

    from summarizer import describe
    frase, tokens = describe("texto del tweet", "gpt-5.5", FakeClient())
    assert frase == "Una frase corta."
    assert tokens == 12
```

`tests/sources/x/test_notes.py`:
```python
import yaml

from sources.x.models import Tweet, QuotedTweet
from sources.x.notes import render_post_note


def _tweet(**kw):
    base = dict(id="123", text="cuerpo crudo\ncon salto", author_username="janedev",
                author_name="Jane Dev", created_at="2026-06-28T14:00:00.000Z")
    base.update(kw)
    return Tweet(**base)


def test_render_has_frontmatter_and_body():
    md = render_post_note(_tweet(), "Frase de descripcion.")
    fm = md.split("---\n")[1]
    parsed = yaml.safe_load(fm)
    assert parsed["type"] == "Recurso"
    assert parsed["subtype"] == "Post"
    assert parsed["source"] == "X"
    assert parsed["tags"] == ["Recursos/Post"]
    assert parsed["description"] == "Frase de descripcion."
    assert "# Post de Jane Dev (@janedev)" in md
    assert "cuerpo crudo\ncon salto" in md
    assert "[@janedev](https://x.com/janedev) (Jane Dev)" in md
    assert "**Fecha:** 2026-06-28" in md
    assert "https://x.com/janedev/status/123" in md
    assert md.endswith("\n")


def test_render_includes_quote_when_present():
    md = render_post_note(_tweet(quoted=QuotedTweet("other", "lo citado")), "d")
    assert "> **Cita a @other:**" in md
    assert "> lo citado" in md


def test_render_omits_quote_and_media_when_absent():
    md = render_post_note(_tweet(), "d")
    assert "Cita a" not in md
    assert "## Media" not in md


def test_render_includes_media_section():
    md = render_post_note(_tweet(media_urls=("https://pbs.twimg.com/a.jpg", "https://v/b.mp4")), "d")
    assert "## Media" in md
    assert "- https://pbs.twimg.com/a.jpg" in md
    assert "- https://v/b.mp4" in md


def test_description_with_colon_stays_valid_yaml():
    md = render_post_note(_tweet(), 'Tema: por qué "esto" importa')
    fm = md.split("---\n")[1]
    assert yaml.safe_load(fm)["description"] == 'Tema: por qué "esto" importa'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_summarizer.py tests/sources/x/test_notes.py -v`
Expected: FAIL (`ImportError: cannot import name 'describe'` / `No module named 'sources.x.notes'`).

- [ ] **Step 3: Implement**

Agregar a `summarizer.py`:
```python
_DESCRIBE_SYSTEM = (
    "Sos un asistente que resume el contenido de un post en español. "
    "Respondé EXCLUSIVAMENTE con un objeto JSON con una clave: "
    '"description" (una sola frase, resumen para búsqueda semántica). '
    "No agregues texto fuera del JSON."
)


def describe(text: str, model: str, client) -> tuple[str, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _DESCRIBE_SYSTEM},
            {"role": "user", "content": f"Contenido del post:\n{text}\n\nDevolvé el JSON con la clave description."},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    obj = json.loads(content)
    if "description" not in obj:
        raise SummaryError("Falta la clave description en la respuesta.")
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", 0) or 0
    return str(obj["description"]), tokens
```

`sources/x/notes.py`:
```python
import json

from sources.x.models import Tweet


def _yaml_scalar(value: str) -> str:
    """Escalar YAML seguro (mismo criterio que notes._yaml_scalar)."""
    return json.dumps(value, ensure_ascii=False)


def render_post_note(tweet: Tweet, description: str) -> str:
    parts = [
        "---\n",
        "tags:\n",
        "  - Recursos/Post\n",
        "type: Recurso\n",
        "subtype: Post\n",
        "source: X\n",
        f"description: {_yaml_scalar(description)}\n",
        "---\n",
        "\n",
        f"# Post de {tweet.author_name} (@{tweet.author_username})\n",
        "\n",
        f"{tweet.text}\n",
    ]
    if tweet.quoted is not None:
        parts.append("\n")
        parts.append(f"> **Cita a @{tweet.quoted.author_username}:**\n")
        for line in tweet.quoted.text.split("\n"):
            parts.append(f"> {line}\n")
    if tweet.media_urls:
        parts.append("\n## Media\n")
        for url in tweet.media_urls:
            parts.append(f"- {url}\n")
    parts.append("\n## Metadatos\n")
    parts.append(f"- **Autor:** [@{tweet.author_username}](https://x.com/{tweet.author_username}) ({tweet.author_name})\n")
    parts.append(f"- **Fecha:** {tweet.created_at[:10]}\n")
    parts.append(f"- **Post:** https://x.com/{tweet.author_username}/status/{tweet.id}\n")
    return "".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_summarizer.py tests/sources/x/test_notes.py -v`
Expected: PASS (todos verdes).

- [ ] **Step 5: Commit**

```bash
git add summarizer.py sources/x/notes.py tests/test_summarizer.py tests/sources/x/test_notes.py
git commit -m "feat: add describe() and X post note rendering

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: `XSource`

**Files:**
- Create: `sources/x/source.py`
- Test: `tests/sources/x/test_source.py`

**Interfaces:**
- Consumes: `config.Config`; `sources.base.RenderedNote`; `sources.x.auth` (`TokenStore`, `get_valid_access_token`, `AuthError`); `sources.x.client` (`get_user_id`, `get_bookmarks`, `save_token_response`... — no); `summarizer.describe`; `sources.x.notes.render_post_note`.
- Produces:
  - `XSource(cfg, openai_client, *, get_valid_access_token=None, get_user_id=None, get_bookmarks=None, describe=None, token_store=None)`:
    - `name = "X"`, `subdir = cfg.x_subdir`.
    - `fetch() -> list[Tweet]` — valida credenciales (si `cfg.x_client_id`/`x_client_secret` faltan → `AuthError` claro); obtiene un access token válido; resuelve `user_id` (usa el cacheado del store, si no lo pide y lo persiste); trae bookmarks.
    - `stem(tweet) -> str` = `tweet.id`.
    - `render(tweet) -> RenderedNote` — arma el texto base (tweet + citado) para el `describe`; llama `describe` → `(frase, tokens)`; `render_post_note(tweet, frase)`; devuelve `RenderedNote(md, tokens)`.
    - Los kwargs permiten inyectar en tests.

- [ ] **Step 1: Write the failing test**

`tests/sources/x/test_source.py`:
```python
from pathlib import Path

import pytest

from config import Config
from sources.base import RenderedNote
from sources.x.auth import AuthError, TokenStore
from sources.x.models import Tweet, QuotedTweet
from sources.x.source import XSource


def _cfg(tmp_path, cid="cid", sec="sec") -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=tmp_path, github_subdir="Recursos/Repositorios",
        git_push=True, gbrain_sync=True, script_dir=tmp_path,
        log_path=tmp_path / "sync.log",
        x_client_id=cid, x_client_secret=sec, x_subdir="Recursos/Posts",
        x_token_path=tmp_path / ".x_token.json",
    )


def _tweet(tid="1"):
    return Tweet(id=tid, text="hola", author_username="jane", author_name="Jane",
                 created_at="2026-06-28T14:00:00.000Z")


def test_name_and_subdir(tmp_path):
    src = XSource(_cfg(tmp_path), openai_client=None)
    assert src.name == "X"
    assert src.subdir == "Recursos/Posts"


def test_stem_is_tweet_id(tmp_path):
    src = XSource(_cfg(tmp_path), openai_client=None)
    assert src.stem(_tweet("42")) == "42"


def test_fetch_raises_when_credentials_missing(tmp_path):
    src = XSource(_cfg(tmp_path, cid=None), openai_client=None)
    with pytest.raises(AuthError):
        src.fetch()


def test_fetch_resolves_user_id_and_returns_bookmarks(tmp_path):
    store = TokenStore(tmp_path / ".x_token.json")
    store.save({"access_token": "at", "refresh_token": "rt",
                "expires_at": "2999-01-01T00:00:00", "user_id": None})
    calls = {}

    def fake_get_user_id(token, **k):
        calls["user_id_fetched"] = True
        return "u1"

    def fake_get_bookmarks(user_id, token, **k):
        calls["user_id_used"] = user_id
        return [_tweet("1"), _tweet("2")]

    src = XSource(
        _cfg(tmp_path), openai_client=None,
        get_valid_access_token=lambda *a, **k: "at",
        get_user_id=fake_get_user_id, get_bookmarks=fake_get_bookmarks,
        token_store=store,
    )
    tweets = src.fetch()
    assert [t.id for t in tweets] == ["1", "2"]
    assert calls["user_id_used"] == "u1"
    # user_id se persiste en el store
    assert store.load()["user_id"] == "u1"


def test_fetch_uses_cached_user_id(tmp_path):
    store = TokenStore(tmp_path / ".x_token.json")
    store.save({"access_token": "at", "refresh_token": "rt",
                "expires_at": "2999-01-01T00:00:00", "user_id": "cached"})

    def fake_get_user_id(token, **k):
        raise AssertionError("no debería pedir user_id")

    src = XSource(
        _cfg(tmp_path), openai_client=None,
        get_valid_access_token=lambda *a, **k: "at",
        get_user_id=fake_get_user_id,
        get_bookmarks=lambda user_id, token, **k: [_tweet("1")],
        token_store=store,
    )
    assert [t.id for t in src.fetch()] == ["1"]


def test_render_builds_note_with_description(tmp_path):
    from sources.x.notes import render_post_note
    seen = {}

    def fake_describe(text, model, client):
        seen["text"] = text
        return "una frase", 9

    src = XSource(_cfg(tmp_path), openai_client=None, describe=fake_describe)
    tw = Tweet(id="1", text="cuerpo", author_username="jane", author_name="Jane",
               created_at="2026-06-28T14:00:00.000Z",
               quoted=QuotedTweet("other", "citado"))
    note = src.render(tw)
    assert isinstance(note, RenderedNote)
    assert note.tokens == 9
    assert note.text == render_post_note(tw, "una frase")
    # el texto que va al LLM incluye cuerpo y citado
    assert "cuerpo" in seen["text"]
    assert "citado" in seen["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/sources/x/test_source.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sources.x.source'`).

- [ ] **Step 3: Implement**

`sources/x/source.py`:
```python
import summarizer
from sources.base import RenderedNote
from sources.x import auth as x_auth
from sources.x import client as x_client
from sources.x.notes import render_post_note


class XSource:
    """Fuente de posts guardados (bookmarks) de X → notas markdown.

    El cuerpo de la nota es el texto crudo del tweet (+ citado + media); el LLM
    solo genera la ``description`` de una línea del frontmatter.
    """
    name = "X"

    def __init__(self, cfg, openai_client, *, get_valid_access_token=None,
                 get_user_id=None, get_bookmarks=None, describe=None, token_store=None):
        self.subdir = cfg.x_subdir
        self._cfg = cfg
        self._openai = openai_client
        self._store = token_store or x_auth.TokenStore(cfg.x_token_path)
        self._get_valid_access_token = get_valid_access_token or x_auth.get_valid_access_token
        self._get_user_id = get_user_id or x_client.get_user_id
        self._get_bookmarks = get_bookmarks or x_client.get_bookmarks
        self._describe = describe or (lambda text: summarizer.describe(text, cfg.openai_model, self._openai))
        # describe puede inyectarse con firma (text, model, client) en tests:
        if describe is not None:
            self._describe = lambda text, _d=describe: _d(text, cfg.openai_model, self._openai)

    def fetch(self):
        if not self._cfg.x_client_id or not self._cfg.x_client_secret:
            raise x_auth.AuthError(
                "Faltan X_CLIENT_ID/X_CLIENT_SECRET en el .env. Configurá la app de X."
            )
        access_token = self._get_valid_access_token(
            self._store, self._cfg.x_client_id, self._cfg.x_client_secret
        )
        data = self._store.load()
        user_id = data.get("user_id")
        if not user_id:
            user_id = self._get_user_id(access_token)
            data["user_id"] = user_id
            self._store.save(data)
        return self._get_bookmarks(user_id, access_token)

    def stem(self, tweet):
        return tweet.id

    def render(self, tweet):
        base = tweet.text
        if tweet.quoted is not None:
            base += f"\n\n[cita a @{tweet.quoted.author_username}]: {tweet.quoted.text}"
        description, tokens = self._describe(base)
        return RenderedNote(render_post_note(tweet, description), tokens)
```

Nota sobre `describe`: en producción se usa `summarizer.describe(text, model, client)`; el wrapper de arriba adapta ambas firmas para que el test pueda inyectar `fake_describe(text, model, client)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/sources/x/test_source.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add sources/x/source.py tests/sources/x/test_source.py
git commit -m "feat: add XSource implementing the Source protocol

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Wiring en `sync.py` — registrar `XSource` + subcomando `auth x` + `--source x`

**Files:**
- Modify: `sync.py`
- Modify: `tests/test_sync.py`

**Interfaces:**
- Consumes: `XSource`, `sources.x.auth`.
- Produces:
  - `build_sources(cfg, openai_client)` ahora devuelve `[GitHubSource(...), XSource(...)]`.
  - `--source` acepta `{github, x}`.
  - Subcomando `auth`: `sync.py auth x` corre el flujo OAuth inicial (`run_x_auth(cfg)`), levantando un servidor loopback, abriendo el navegador y persistiendo el token. La lógica testeable (armado de URL, intercambio) ya está en `sources.x.auth`; `run_x_auth` es glue.

- [ ] **Step 1: Write the failing test**

Reemplazar/expandir `tests/test_sync.py` con:
```python
from pathlib import Path

from config import Config
from sync import build_sources, build_parser


def _cfg() -> Config:
    return Config(
        openai_api_key="k", openai_model="gpt-5.5",
        digital_brain_path=Path("/brain"), github_subdir="Recursos/Repositorios",
        git_push=True, gbrain_sync=True, script_dir=Path("/s"),
        log_path=Path("/s/sync.log"),
        x_client_id="cid", x_client_secret="sec", x_subdir="Recursos/Posts",
        x_token_path=Path("/s/.x_token.json"),
    )


def test_build_sources_includes_github_and_x():
    names = [s.name for s in build_sources(_cfg(), openai_client=None)]
    assert names == ["GitHub", "X"]


def test_parser_accepts_source_x():
    args = build_parser().parse_args(["--source", "x", "--limit", "2"])
    assert args.source == "x"
    assert args.limit == 2
    assert args.command is None


def test_parser_accepts_auth_subcommand():
    args = build_parser().parse_args(["auth", "x"])
    assert args.command == "auth"
    assert args.provider == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_sync.py -v`
Expected: FAIL (`ImportError: cannot import name 'build_parser'` / X no registrada).

- [ ] **Step 3: Implement**

En `sync.py`:

1. Import: agregar `from sources.x.source import XSource` y `from sources.x import auth as x_auth`, más `import http.server`, `import secrets`, `import threading`, `import urllib.parse`, `import webbrowser`.

2. `build_sources`:
```python
def build_sources(cfg, openai_client) -> list:
    return [GitHubSource(cfg, openai_client), XSource(cfg, openai_client)]
```

3. Extraer el parser a una función y agregar el subcomando `auth`:
```python
REDIRECT_URI = "http://127.0.0.1:8723/callback"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza recursos externos (repos faveados, posts de X, ...) al digital brain."
    )
    parser.add_argument("--source", choices=["github", "x"], default=None,
                        help="Correr solo una fuente (default: todas).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Procesar como máximo N items nuevos por fuente (corrida de prueba).")
    sub = parser.add_subparsers(dest="command")
    auth_p = sub.add_parser("auth", help="Autorizar una fuente (flujo OAuth inicial).")
    auth_p.add_argument("provider", choices=["x"], help="Proveedor a autorizar.")
    return parser
```

4. `run_x_auth` (glue de OAuth; no unit-testeado — verificación manual):
```python
def run_x_auth(cfg) -> int:
    if not cfg.x_client_id or not cfg.x_client_secret:
        print("ERROR: faltan X_CLIENT_ID/X_CLIENT_SECRET en el .env.", file=sys.stderr)
        return 1
    verifier, challenge = x_auth.generate_pkce()
    state = secrets.token_urlsafe(16)
    url = x_auth.build_authorize_url(cfg.x_client_id, REDIRECT_URI, challenge, state)

    holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            holder["code"] = q.get("code", [None])[0]
            holder["state"] = q.get("state", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Autorizacion recibida. Ya podes cerrar esta pestana.")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8723), Handler)
    print(f"Abriendo el navegador para autorizar X...\nSi no se abre, entrá a:\n{url}")
    webbrowser.open(url)
    server.handle_request()  # atiende el único redirect y sigue
    server.server_close()

    if not holder.get("code") or holder.get("state") != state:
        print("ERROR: no se recibió un code válido (state mismatch).", file=sys.stderr)
        return 1
    body = x_auth.exchange_code(cfg.x_client_id, cfg.x_client_secret,
                                holder["code"], verifier, REDIRECT_URI)
    store = x_auth.TokenStore(cfg.x_token_path)
    x_auth.save_token_response(store, body)
    print(f"Token guardado en {cfg.x_token_path}. Ya podés correr `sync.py --source x`.")
    return 0
```

5. En `main`, después de parsear, manejar el subcomando antes del flujo normal:
```python
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.command == "auth":
        return run_x_auth(cfg)

    client = OpenAI(api_key=cfg.openai_api_key)
    sources = build_sources(cfg, client)
    if args.source:
        sources = [s for s in sources if s.name.lower() == args.source]
    # ... (resto igual que antes: loop de fuentes, downstream, logging)
```
Conservar el resto del loop de `main` tal cual (el existente del Plan 1).

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_sync.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify CLI wiring**

Run: `./venv/bin/python sync.py --help` y `./venv/bin/python sync.py auth --help`
Expected: `--source {github,x}` y el subcomando `auth {x}` aparecen.

- [ ] **Step 6: Commit**

```bash
git add sync.py tests/test_sync.py
git commit -m "feat: register XSource and add 'auth x' subcommand in sync.py

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Docs, suite completa y verificación diferida

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:** ninguna nueva.

- [ ] **Step 1: Actualizar `.env.example`**

Agregar al final:
```
X_CLIENT_ID=
X_CLIENT_SECRET=
X_SUBDIR=Recursos/Posts
```

- [ ] **Step 2: Actualizar `README.md`**

Agregar una sección de la fuente X: cómo crear la app de X (confidential client, redirect URI `http://127.0.0.1:8723/callback`, scopes), correr `./venv/bin/python sync.py auth x` una vez, y que después `sync.py` la sincroniza junto con GitHub. Documentar que el token se guarda en `.x_token.json` (gitignored) y rota solo.

- [ ] **Step 3: Correr TODA la suite**

Run: `./venv/bin/python -m pytest -v`
Expected: PASS — todos los tests de GitHub (Plan 1) y X (Plan 2) verdes. Confirmar que `tests/test_notes.py` y `tests/test_runlog.py` no fueron modificados.

- [ ] **Step 4: Verificación diferida (requiere credenciales reales de X)**

Estos pasos NO se pueden automatizar sin la app de X del usuario. Documentarlos en el reporte como pendientes de verificación manual:
1. Completar `X_CLIENT_ID`/`X_CLIENT_SECRET` en `.env`.
2. `./venv/bin/python sync.py auth x` → autorizar en el navegador → confirmar que se crea `.x_token.json`.
3. `X_SUBDIR=Recursos/Posts DIGITAL_BRAIN_PATH=/tmp/brain_smoke GIT_PUSH=false GBRAIN_SYNC=false ./venv/bin/python sync.py --source x --limit 1` → confirmar que crea `/tmp/brain_smoke/Recursos/Posts/<tweet_id>.md` con el formato del spec. Limpieza: `rm -rf /tmp/brain_smoke`.

- [ ] **Step 5: Cambio manual en el digital brain (otro repo)**

Documentar (no es código de este repo): en el `CLAUDE.md` del vault, agregar `X` al vocabulario de `source` y `Post` al de `subtype`.

- [ ] **Step 6: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document X bookmarks source setup and env

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (Plan 2 del spec):**
- OAuth 2.0 PKCE + refresh con rotación → Tasks 3, 4. ✓
- Cliente de bookmarks API v2 con expansiones + paginación → Task 5. ✓
- Modelo `Tweet` (texto, autor, fecha, citado, media) → Task 2. ✓
- Render de nota: texto crudo + citado + media + `description` LLM → Task 6. ✓
- `XSource` sobre la abstracción → Task 7. ✓
- `sync.py auth x` + registro + `--source x` → Task 8. ✓
- Config de X + `.x_token.json` gitignored → Task 1. ✓
- Credenciales faltantes no rompen otras fuentes → Task 7 (`fetch` levanta `AuthError`, capturado por el loop de `process_source`... **ver nota abajo**).
- CLAUDE.md del brain (source X / subtype Post) → Task 9 Step 5 (manual, otro repo). ✓

**⚠️ Nota de integración a validar en review:** `process_source` (Plan 1) captura excepciones de `source.render`, pero `source.fetch()` se llama fuera del try/except por-item. Si `XSource.fetch()` levanta `AuthError` (credenciales faltantes / refresh revocado), el `process_source` actual lo propagaría y cortaría `sync.py`, rompiendo las otras fuentes — contradiciendo la constraint "no rompe las otras fuentes". **Resolución:** en Task 8, el loop de `main` en `sync.py` debe envolver la llamada a `process_source(cfg, source, ...)` en un try/except que registre el fallo de esa fuente (como error en su `RunStats`/log) y continúe con la siguiente. Agregar este manejo en Task 8 Step 3 (punto 5, en el loop de `main`): capturar excepciones de `process_source`, marcar la fuente como FALLO en el log, y seguir. Añadir un test en `tests/test_sync.py` que verifique que una fuente que falla en `fetch` no impide correr las demás (inyectar dos fuentes fake, una que rompe en fetch).

**Placeholder scan:** sin TBD/TODO; código completo en cada step.

**Type consistency:** `Tweet`/`QuotedTweet` consistentes entre Tasks 2, 5, 6, 7. `RenderedNote(text, tokens)` igual que Plan 1. `get_valid_access_token(store, client_id, client_secret, ...)` consistente entre Task 4 (def) y Task 7 (uso). `describe(text, model, client) -> (str, int)` consistente entre Task 6 (def) y Task 7 (uso vía wrapper). `parse_bookmarks`/`get_bookmarks` firmas consistentes entre Task 5 y Task 7.

**Corrección aplicada al plan:** se agrega a Task 8 el manejo de fallo por-fuente en `main` (ver nota de integración), necesario para cumplir la constraint de aislamiento entre fuentes.
