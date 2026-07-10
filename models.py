from dataclasses import dataclass


@dataclass(frozen=True)
class RepoInfo:
    full_name: str          # "owner/repo"
    owner: str               # "owner"
    name: str                # "repo"
    html_url: str
    stars: int
    description: str | None


@dataclass(frozen=True)
class Summary:
    summary: str            # párrafo para el cuerpo
    description: str        # una frase para el frontmatter
