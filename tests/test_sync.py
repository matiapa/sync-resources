from pathlib import Path

from config import Config
from sync import build_sources, build_parser, main


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


def test_source_fetch_failure_does_not_prevent_other_sources(tmp_path, monkeypatch):
    """AuthError (o cualquier excepción) en fetch() de una fuente no debe cortar
    el resto de las fuentes ni el exit code debe quedar en 0."""
    from dataclasses import dataclass, field

    from sources.base import RenderedNote

    @dataclass
    class FakeSource:
        name: str
        subdir: str
        items: list = field(default_factory=list)
        fails: bool = False

        def fetch(self):
            if self.fails:
                raise RuntimeError("boom in fetch")
            return self.items

        def stem(self, item):
            return item

        def render(self, item):
            return RenderedNote(f"# {item}\n", 0)

    broken = FakeSource(name="Broken", subdir="broken", fails=True)
    ok = FakeSource(name="Ok", subdir="ok", items=["a", "b"])

    monkeypatch.setattr("sync.build_sources", lambda cfg, client: [broken, ok])
    monkeypatch.setattr("sync.load_config", lambda: _cfg().__class__(
        **{**_cfg().__dict__, "digital_brain_path": tmp_path,
           "log_path": tmp_path / "sync.log", "git_push": False, "gbrain_sync": False}
    ))
    monkeypatch.setattr("sync.OpenAI", lambda api_key: None)
    monkeypatch.setattr("sync.load_dotenv", lambda: None)

    exit_code = main([])

    # La fuente Ok igual corrió y creó sus notas, pese a que Broken falló en fetch.
    assert (tmp_path / "ok" / "a.md").exists()
    assert (tmp_path / "ok" / "b.md").exists()
    # El exit code refleja el fallo de la fuente Broken.
    assert exit_code == 1
