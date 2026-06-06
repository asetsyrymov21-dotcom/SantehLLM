import pytest

from app.schemas import AssistantMemoryStoreRequest
from app.services.assistant_memory import (
    AssistantMemoryService,
    normalize_memory_question,
)


def test_normalize_memory_question_collapses_noise():
    assert (
        normalize_memory_question("  Как   загрузить остатки?!  ")
        == "как загрузить остатки"
    )


def test_assistant_memory_rejects_operational_intents_without_db():
    service = AssistantMemoryService(session=None)
    payload = AssistantMemoryStoreRequest(
        question="Есть G1017 5 шт?",
        intent="stock_check",
        answer_text="Остаток 10",
    )

    with pytest.raises(ValueError, match="Operational"):
        service.store(payload)
