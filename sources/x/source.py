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
        describe_impl = describe or summarizer.describe
        self._describe = lambda text: describe_impl(text, cfg.openai_model, self._openai)

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
