"""Провайдеро-независимый интерфейс LLM. Остальной код знает только эти типы."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "function"]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema объекта аргументов


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str = ""
    tool_call: ToolCall | None = None  # для role="assistant", если модель вызвала функцию
    name: str | None = None  # для role="function": имя функции, чей это результат


@dataclass(slots=True)
class LLMReply:
    text: str = ""
    tool_call: ToolCall | None = None


class LLMClient(Protocol):
    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMReply: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def close(self) -> None: ...
