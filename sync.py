import argparse
import http.server
import secrets
import sys
import urllib.parse
import webbrowser
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

import downstream
from config import ConfigError, load_config
from pipeline import process_source
from runlog import RunStats, append_log, format_summary
from sources.github.source import GitHubSource
from sources.x import auth as x_auth
from sources.x.source import XSource

REDIRECT_URI = "http://127.0.0.1:8723/callback"


def build_sources(cfg, openai_client) -> list:
    return [GitHubSource(cfg, openai_client), XSource(cfg, openai_client)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza recursos externos (repos faveados, posts de X, ...) al digital brain."
    )
    parser.add_argument(
        "--source",
        choices=["github", "x"],
        default=None,
        help="Correr solo una fuente (default: todas).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como máximo N items nuevos por fuente (corrida de prueba).",
    )
    sub = parser.add_subparsers(dest="command")
    auth_p = sub.add_parser("auth", help="Autorizar una fuente (flujo OAuth inicial).")
    auth_p.add_argument("provider", choices=["x"], help="Proveedor a autorizar.")
    return parser


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

    exit_code = 0
    for source in sources:
        # disable=None apaga la barra en no-TTY (cron), evitando ensuciar sync.log.
        progress = lambda it, s=source: tqdm(
            it, desc=f"Sincronizando {s.name}", unit="item", disable=None
        )
        try:
            stats = process_source(cfg, source, limit=args.limit, progress=progress)
        except Exception as exc:  # noqa: BLE001 - fetch() puede fallar (ej. AuthError
            # de X sin credenciales / refresh token revocado); no debe cortar las
            # demás fuentes, solo registrarse como fallo de ESTA fuente.
            stats = RunStats()
            stats.errors.append((f"<{source.name}>", str(exc)))
            stats.git_ok = False
            summary_text = format_summary(stats, datetime.now())
            append_log(cfg.log_path, summary_text)
            print(summary_text, end="")
            exit_code = 1
            continue

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
