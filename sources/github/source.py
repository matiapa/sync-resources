import github_client
import notes
import summarizer
from sources.base import RenderedNote


class GitHubSource:
    """Fuente de repos *starred* de GitHub → notas markdown.

    El cuerpo de la nota es un resumen del README generado por LLM (comportamiento
    heredado de ``sync_repos``). Ver ``notes.render_note`` para el formato.
    """
    name = "GitHub"

    def __init__(self, cfg, openai_client, *, get_starred=None, get_readme=None, summarize=None):
        self.subdir = cfg.github_subdir
        self._get_starred = get_starred or github_client.get_starred_repos
        self._get_readme = get_readme or github_client.get_readme
        self._summarize = summarize or (
            lambda fn, text: summarizer.summarize(fn, text, cfg.openai_model, openai_client)
        )

    def fetch(self):
        return self._get_starred()

    def stem(self, repo):
        return repo.full_name.replace("/", "-")

    def render(self, repo):
        text = self._get_readme(repo.full_name) or repo.description or repo.full_name
        summary, tokens = self._summarize(repo.full_name, text)
        return RenderedNote(notes.render_note(repo, summary), tokens)
