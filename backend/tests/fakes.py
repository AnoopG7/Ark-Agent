"""A scripted chat model for deterministic, offline graph tests."""

from collections.abc import Callable, Sequence
from itertools import count
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

_ids = count(1)

Script = AIMessage | Callable[[list[BaseMessage]], AIMessage]


def call(name: str, **args: Any) -> dict:
    return {"name": name, "args": args, "id": f"call_{next(_ids)}", "type": "tool_call"}


def ai(*calls: dict, text: str = "") -> AIMessage:
    return AIMessage(content=text, tool_calls=list(calls))


class FakeToolCallingModel(BaseChatModel):
    """Returns scripted responses in order; records every prompt it receives."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responses: list[Any]
    prompts: list[list[BaseMessage]] = Field(default_factory=list)
    error: Exception | None = None

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeToolCallingModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        if self.error is not None:
            raise self.error
        self.prompts.append(list(messages))
        if not self.responses:
            raise AssertionError("FakeToolCallingModel ran out of scripted responses")
        nxt = self.responses.pop(0)
        msg = nxt(messages) if callable(nxt) else nxt
        msg = msg.model_copy(update={"id": msg.id or f"ai_{next(_ids)}"})
        return ChatResult(generations=[ChatGeneration(message=msg)])
