from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RenderedNote:
    """Nota lista para escribir en disco.

    ``tokens`` es el consumo OpenAI usado para renderizarla (0 si la fuente
    no usa LLM).
    """
    text: str
    tokens: int = 0


@runtime_checkable
class Source(Protocol):
    """Una fuente de recursos a sincronizar (GitHub, X, ...).

    El driver genérico (``pipeline.process_source``) solo depende de esta
    interfaz: obtiene los items, deriva un ID estable por item para el nombre
    de archivo, y renderiza la nota.
    """
    name: str        # etiqueta legible: "GitHub", "X"
    subdir: str      # subcarpeta destino dentro del digital brain

    def fetch(self) -> list:
        """Trae los items de la fuente (repos, tweets, ...)."""
        ...

    def stem(self, item) -> str:
        """ID estable del item, sin extensión: es el nombre de archivo."""
        ...

    def render(self, item) -> "RenderedNote":
        """Arma la nota del item (incluye llamadas a LLM si la fuente las usa)."""
        ...
