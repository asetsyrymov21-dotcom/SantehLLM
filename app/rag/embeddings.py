import os
from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(texts: list[str], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    resp = get_client().embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


GEN_MODEL = os.getenv("GEN_MODEL", "gpt-4.1-mini")  # можно поменять


def generate_answer(prompt: str, model: str | None = None) -> str:
    """
    Делает финальный ответ на основе prompt (контекст + вопрос).
    """
    use_model = model or GEN_MODEL

    resp = get_client().chat.completions.create(
        model=use_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Отвечай строго по контексту. "
                    "Если в контексте нет ответа — скажи: "
                    '"Не знаю по предоставленным данным".'
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,  # чтобы меньше "фантазировал"
    )
    return (resp.choices[0].message.content or "").strip()
