import json
import logging

from gigachat import GigaChat
from gigachat.models import Chat, Function, FunctionCall, FunctionParameters, Messages

from app.llm.base import ChatMessage, LLMReply, ToolCall, ToolSpec
from app.tls import sber_ssl_context

log = logging.getLogger(__name__)


class GigaChatClient:
    def __init__(
        self,
        credentials: str,
        scope: str,
        model: str,
        ca_bundle: str = "",
        embeddings_model: str = "Embeddings",
    ):
        self._embeddings_model = embeddings_model
        self._g = GigaChat(
            credentials=credentials,
            scope=scope,
            model=model,
            ssl_context=sber_ssl_context(ca_bundle),
            timeout=30,
        )

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMReply:
        chat = Chat(
            messages=[_to_giga(m) for m in messages],
            functions=[_tool_to_giga(t) for t in tools] or None,
            function_call="auto" if tools else None,
            temperature=0.1,
        )
        resp = await self._g.achat(chat)
        msg = resp.choices[0].message
        log.debug("gigachat usage=%s", resp.usage.total_tokens)
        if msg.function_call:
            args = msg.function_call.arguments or {}
            if isinstance(args, str):
                args = json.loads(args)
            return LLMReply(tool_call=ToolCall(msg.function_call.name, args))
        return LLMReply(text=msg.content or "")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._g.aembeddings(texts, model=self._embeddings_model)
        return [item.embedding for item in sorted(resp.data, key=lambda d: d.index)]

    async def close(self) -> None:
        await self._g.aclose()


def _to_giga(m: ChatMessage) -> Messages:
    if m.role == "assistant" and m.tool_call:
        return Messages(
            role="assistant",
            content="",
            function_call=FunctionCall(name=m.tool_call.name, arguments=m.tool_call.arguments),
        )
    if m.role == "function":
        return Messages(role="function", name=m.name, content=m.content)
    return Messages(role=m.role, content=m.content)


def _tool_to_giga(t: ToolSpec) -> Function:
    return Function(
        name=t.name,
        description=t.description,
        parameters=FunctionParameters(**t.parameters),
    )
