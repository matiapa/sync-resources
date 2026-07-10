import json

from models import Summary


class SummaryError(Exception):
    pass


_SYSTEM = (
    "Sos un asistente que resume repositorios de GitHub en español. "
    "Respondé EXCLUSIVAMENTE con un objeto JSON con dos claves: "
    '"summary" (un párrafo que describe qué hace el repositorio) y '
    '"description" (una sola frase, resumen para búsqueda semántica). '
    "No agregues texto fuera del JSON."
)


def build_messages(full_name: str, text: str) -> list[dict]:
    user = (
        f"Repositorio: {full_name}\n\n"
        f"Contenido base (README o descripción):\n{text}\n\n"
        "Devolvé el JSON con las claves summary y description."
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_response(content: str) -> Summary:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # remove leading fence (```json or ```) and trailing fence
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SummaryError(f"JSON inválido del modelo: {exc}") from exc
    if "summary" not in obj or "description" not in obj:
        raise SummaryError("Faltan claves summary/description en la respuesta.")
    return Summary(summary=str(obj["summary"]), description=str(obj["description"]))


def summarize(full_name: str, text: str, model: str, client) -> tuple[Summary, int]:
    response = client.chat.completions.create(
        model=model,
        messages=build_messages(full_name, text),
        response_format={"type": "json_object"},
    )
    summary = parse_response(response.choices[0].message.content)
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", 0) or 0
    return summary, tokens


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
