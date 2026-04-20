# base.py
from dataclasses import dataclass, field
from typing import Any, Iterator
from abc import ABC, abstractmethod


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LLMConfig:
    model: str = "gpt-4o-mini"
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30
    stream: bool = False


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total(self):
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    model: str
    provider: str
    tool_calls: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class AbstractLLMProvider(ABC):

    @abstractmethod
    def complete(self, messages: list, config: LLMConfig) -> LLMResponse:
        pass

    @abstractmethod
    def stream(self, messages: list, config: LLMConfig) -> Iterator[str]:
        pass

    @abstractmethod
    def count_tokens(self, messages: list, model: str) -> int:
        pass