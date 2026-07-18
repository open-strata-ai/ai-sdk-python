"""First-class domain objects (DESIGN §2.2).

``Tool``, ``Session``, ``Retriever``, and the unified ``OpenStrataError``
(DESIGN §9.1). They depend only on the port protocols and the value types in
``models`` — never on a framework. (``ObjectSchema`` / ``ModelBinding`` /
``Guardrails`` live in ``models.py`` so the dependency points one way.)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from openstrata_sdk.domain.models import RAGHit
from openstrata_sdk.domain.ports import Cache, RAG, VectorStore


class Tool:
    """Declarative tool with a JSON-Schema-ish input and a handler (DESIGN §4.3.2)."""

    _registry: Dict[str, "Tool"] = {}

    def __init__(
        self,
        name: str,
        input_schema=None,
        handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.name = name
        self.input_schema = input_schema
        self._handler = handler

    @classmethod
    def register(cls, name: str, input_schema=None):
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            cls._registry[name] = cls(name, input_schema, fn)
            return fn

        return decorator

    @classmethod
    def get(cls, name: str) -> Optional["Tool"]:
        return cls._registry.get(name)

    @classmethod
    def all(cls) -> Dict[str, "Tool"]:
        return dict(cls._registry)

    def call(self, **kwargs: Any) -> Any:
        if self._handler is None:
            raise OpenStrataError(code="TOOL_NO_HANDLER", port="Tool",
                                  message=f"tool {self.name!r} has no handler")
        return self._handler(**kwargs)


class Session:
    """Multi-turn session / working-memory handle bound to a Cache SPI (DESIGN §4.3.4)."""

    def __init__(self, user_id: str, cache: Cache, ttl: float = 3600.0) -> None:
        self.user_id = user_id
        self._cache = cache
        self._ttl = ttl
        self._prefix = f"session:{user_id}:"

    def set_working_memory_ttl(self, ttl: float) -> None:
        self._ttl = ttl

    def put(self, key: str, value: bytes) -> None:
        self._cache.set(self._prefix + key, value, self._ttl)

    def get(self, key: str) -> Optional[bytes]:
        return self._cache.get(self._prefix + key)

    def remember(self, key: str, text: str) -> None:
        self.put(key, text.encode("utf-8"))

    def recall(self, key: str) -> Optional[str]:
        v = self.get(key)
        return v.decode("utf-8") if v is not None else None


class Retriever:
    """Knowledge-base retrieval over a VectorStore + RAG SPI (DESIGN §10.4 / §4.5)."""

    def __init__(self, kb_id: str, vector_store: VectorStore, rag: Optional[RAG] = None) -> None:
        self.kb_id = kb_id
        self._vs = vector_store
        self._rag = rag

    def retrieve(self, query: str, top_k: int = 5) -> List[RAGHit]:
        if self._rag is not None:
            return self._rag.retrieve(query, self.kb_id, top_k)
        return []


class OpenStrataError(Exception):
    """Unified SDK error model (DESIGN §9.1).

    ``retryable`` hints the upper layer to route to ``fallback_chain`` rather
    than retrying inline (avoids avalanches).
    """

    def __init__(self, code: str, port: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.port = port
        self.message = message
        self.retryable = retryable

    def __str__(self) -> str:
        return f"[{self.code}] ({self.port}) {self.message}"
