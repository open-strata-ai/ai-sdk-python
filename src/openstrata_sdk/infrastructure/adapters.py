"""Default SPI adapters (④ infrastructure layer).

All ports have a stdlib-only default so the SDK is usable and testable offline
(no network, no third-party services). Production hosts replace any of these by
injecting their own implementation through ``Client(...)`` (dependency
inversion). The only adapter that touches the network is :class:`HTTPGateway`,
which lazily imports ``httpx`` and is only used when a real base URL is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from typing import AsyncIterator, Dict, List, Optional

from openstrata_sdk.domain.models import (
    AgentHandle,
    AgentSpec,
    ChatRequest,
    ChatResponse,
    DeployHandle,
    DeploySpec,
    Doc,
    EmbedRequest,
    EmbedResponse,
    EvalReport,
    EvalSpec,
    FineTuneHandle,
    FineTuneSpec,
    GatewayRequest,
    GatewayResponse,
    Hit,
    RAGHit,
    RerankRequest,
    RerankResponse,
    RerankResult,
    SandboxResult,
    Span,
    StreamChunk,
    TenantConfig,
    TenantContext,
    WorkflowHandle,
    WorkflowSpec,
)


def _last_user_text(req: ChatRequest) -> str:
    for m in reversed(req.messages):
        if m.role == "user":
            return m.content
    return req.messages[-1].content if req.messages else ""


# --------------------------------------------------------------------------- #
# LLMProvider
# --------------------------------------------------------------------------- #
class EchoLLMProvider:
    """In-memory echo provider — deterministic, offline, for dev/test."""

    def chat(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            id="echo",
            model=req.model or "echo",
            content=f"echo: {_last_user_text(req)}",
            finish_reason="stop",
        )

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        dim = 8
        vectors: List[List[float]] = []
        for text in req.inputs:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((h[i] % 200) - 100) / 100.0 for i in range(dim)]
            vectors.append(vec)
        return EmbedResponse(model=req.model or "echo", vectors=vectors)

    def rerank(self, req: RerankRequest) -> RerankResponse:
        ranked = sorted(
            enumerate(req.docs),
            key=lambda t: -len(t[1]),
        )
        top_k = req.top_k or len(ranked)
        results = [
            RerankResult(index=i, score=1.0 - 0.1 * rank, doc=doc)
            for rank, (i, doc) in enumerate(ranked[:top_k])
        ]
        return RerankResponse(model=req.model or "echo", results=results)

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]:
        text = f"echo: {_last_user_text(req)}"
        for i, ch in enumerate(text):
            yield StreamChunk(delta=ch, index=i)
        yield StreamChunk(delta="", finish_reason="stop", index=len(text))


# --------------------------------------------------------------------------- #
# VectorStore
# --------------------------------------------------------------------------- #
class InMemoryVectorStore:
    """Cosine-similarity vector store backed by a plain dict."""

    def __init__(self) -> None:
        self._collections: Dict[str, Dict[str, Doc]] = {}

    def upsert(self, collection: str, docs: List[Doc]) -> None:
        self._collections.setdefault(collection, {})
        for d in docs:
            self._collections[collection][d.id] = d

    def search(self, collection: str, vec: List[float], top_k: int) -> List[Hit]:
        docs = self._collections.get(collection, {})
        scored = []
        for d in docs.values():
            if not d.vector:
                continue
            scored.append((_cosine(vec, d.vector), d))
        scored.sort(key=lambda t: -t[0])
        return [
            Hit(id=d.id, score=score, text=d.text, metadata=d.metadata)
            for score, d in scored[:top_k]
        ]

    def delete(self, collection: str, ids: List[str]) -> None:
        store = self._collections.get(collection)
        if store:
            for i in ids:
                store.pop(i, None)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
class InMemoryCache:
    """TTL-aware in-memory cache; ``None`` on miss or expiry (DESIGN §2.3)."""

    def __init__(self) -> None:
        self._store: Dict[str, tuple[bytes, float]] = {}

    def get(self, key: str) -> Optional[bytes]:
        item = self._store.get(key)
        if item is None:
            return None
        val, exp = item
        # ttl <= 0 means immediate expiry; otherwise expire once wall-clock passes.
        if exp <= 0 or time.time() > exp:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, val: bytes, ttl: float) -> None:
        exp = time.time() + ttl if ttl and ttl > 0 else 0.0
        self._store[key] = (val, exp)


# --------------------------------------------------------------------------- #
# AgentRuntime
# --------------------------------------------------------------------------- #
class LocalAgentRuntime:
    """Local map executor — loads a spec and echoes input on run."""

    def __init__(self) -> None:
        self._handles: Dict[str, AgentHandle] = {}
        self._seq = 0

    def load(self, spec: AgentSpec) -> AgentHandle:
        self._seq += 1
        handle = AgentHandle(
            id=spec.metadata.get("name") or f"agent-{self._seq}",
            spec_metadata=spec.metadata,
            model=spec.model_binding.preferred if spec.model_binding else None,
        )
        self._handles[handle.id] = handle
        return handle

    def run(self, handle: AgentHandle, input: Dict) -> Dict:
        return {"agent": handle.id, "output": input}


# --------------------------------------------------------------------------- #
# Auth / Tracing
# --------------------------------------------------------------------------- #
class LocalAuth:
    """Dev-mode auth: mints a local tenant context from the token."""

    def validate_token(self, token: str) -> TenantContext:
        if not token:
            return TenantContext(tenant_id="anonymous", roles=[])
        return TenantContext(tenant_id=token, roles=["local"])


class _Span:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ctx: Dict[str, object] = {}

    def end(self) -> None:
        self.ctx["ended"] = True


class NoOpTracing:
    """No-op tracing (OTel baseline) — records nothing."""

    def start_span(self, name: str) -> Span:
        return Span(name=name, ctx={})


# --------------------------------------------------------------------------- #
# Logging / pass-through adapters for consumption ports
# --------------------------------------------------------------------------- #
class LoggingGateway:
    """Offline gateway: echoes the request back as a 200 response."""

    def invoke(self, req: GatewayRequest) -> GatewayResponse:
        return GatewayResponse(status=200, body={"echo": req.path, "method": req.method})


class LoggingRAG:
    def retrieve(self, query: str, kb_id: str, top_k: int) -> List[RAGHit]:
        return []


class LoggingLowCode:
    def export_spec(self, canvas_id: str) -> AgentSpec:
        return AgentSpec(metadata={"name": f"exported-{canvas_id}", "canvas_id": canvas_id})


class LoggingWorkflow:
    def submit(self, spec: WorkflowSpec) -> WorkflowHandle:
        return WorkflowHandle(id=f"wf-{spec.name}", status="submitted")


class LoggingSandbox:
    def execute(self, code: str, language: str) -> SandboxResult:
        return SandboxResult(stdout="", stderr="", exit_code=0)


class LoggingCICD:
    def deploy(self, spec: DeploySpec) -> DeployHandle:
        return DeployHandle(id=f"dep-{spec.name}", status="deploying")


class LoggingMultiTenancy:
    def resolve_tenant(self, tenant_id: str) -> TenantConfig:
        return TenantConfig(tenant_id=tenant_id)


class LoggingMLOps:
    def submit_fine_tune(self, spec: FineTuneSpec) -> FineTuneHandle:
        return FineTuneHandle(id=f"ft-{spec.base_model}", status="queued")


class LoggingEval:
    def run_eval(self, spec: EvalSpec) -> EvalReport:
        return EvalReport(score=1.0, details={"spec": spec.name})


# --------------------------------------------------------------------------- #
# HTTPGateway (network) — uses httpx lazily so the SDK imports without it.
# --------------------------------------------------------------------------- #
class HTTPGateway:
    """Production gateway over httpx (OpenAI-compatible). Lazy-imports httpx."""

    def __init__(self, base_url: str, token: Optional[str] = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def invoke(self, req: GatewayRequest) -> GatewayResponse:
        import httpx  # local import keeps the SDK importable without httpx

        headers = dict(req.headers or {})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                req.method,
                f"{self._base_url}{req.path}",
                json=req.body,
                headers=headers,
            )
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text}
            return GatewayResponse(status=resp.status_code, body=body, headers=dict(resp.headers))


__all__ = [
    "EchoLLMProvider",
    "InMemoryVectorStore",
    "InMemoryCache",
    "LocalAgentRuntime",
    "LocalAuth",
    "NoOpTracing",
    "LoggingGateway",
    "LoggingRAG",
    "LoggingLowCode",
    "LoggingWorkflow",
    "LoggingSandbox",
    "LoggingCICD",
    "LoggingMultiTenancy",
    "LoggingMLOps",
    "LoggingEval",
    "HTTPGateway",
]
