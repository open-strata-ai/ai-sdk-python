"""15 platform SPI port protocols (dependency inversion, DESIGN §2.3 / §6).

Every port is a ``typing.Protocol`` (structural subtyping — no explicit
inheritance required) and is free of any framework/external dependency
(§15.5.2 domain-layer prohibition). Method signatures are semantically
consistent with ai-sdk-go / ai-sdk-java for cross-language contract parity.
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional, Protocol

from openstrata_sdk.domain.models import (
    AgentHandle,
    AgentSpec,
    ChatRequest,
    ChatResponse,
    DeployHandle,
    DeploySpec,
    Doc,
    EvalReport,
    EvalSpec,
    FineTuneHandle,
    FineTuneSpec,
    GatewayRequest,
    GatewayResponse,
    Hit,
    RAGHit,
    SandboxResult,
    Span,
    TenantConfig,
    TenantContext,
    WorkflowHandle,
    WorkflowSpec,
)


class LLMProvider(Protocol):
    """Platform LLMProvider SPI (§4.4.4), interface_versions: 1.0.0."""

    def chat(self, req: ChatRequest) -> ChatResponse: ...
    def embed(self, req: "EmbedRequest") -> "EmbedResponse": ...
    def rerank(self, req: "RerankRequest") -> "RerankResponse": ...
    def stream(self, req: ChatRequest) -> AsyncIterator["StreamChunk"]: ...


class VectorStore(Protocol):
    """Platform VectorStore SPI (§10.4), interface_versions: 1.0.0."""

    def upsert(self, collection: str, docs: List[Doc]) -> None: ...
    def search(self, collection: str, vec: List[float], top_k: int) -> List[Hit]: ...
    def delete(self, collection: str, ids: List[str]) -> None: ...


class AgentRuntime(Protocol):
    """Platform AgentRuntime SPI (§10.6 / §4.3.5), interface_versions: 1.0.0."""

    def load(self, spec: AgentSpec) -> AgentHandle: ...
    def run(self, handle: AgentHandle, input: Dict) -> Dict: ...


class Cache(Protocol):
    """Platform Cache SPI (§4.3.4), interface_versions: 1.0.0."""

    def get(self, key: str) -> Optional[bytes]: ...
    def set(self, key: str, val: bytes, ttl: float) -> None: ...


class Gateway(Protocol):
    """Platform Gateway SPI (§4.4.1), interface_versions: 1.0.0."""

    def invoke(self, req: GatewayRequest) -> GatewayResponse: ...


class Tracing(Protocol):
    """Platform Tracing SPI (§4.8), interface_versions: 1.0.0."""

    def start_span(self, name: str) -> Span: ...


class Auth(Protocol):
    """Platform Auth SPI, interface_versions: 1.0.0."""

    def validate_token(self, token: str) -> TenantContext: ...


class RAG(Protocol):
    """Platform RAG SPI, interface_versions: 1.0.0."""

    def retrieve(self, query: str, kb_id: str, top_k: int) -> List[RAGHit]: ...


class LowCode(Protocol):
    """Platform LowCode SPI, interface_versions: 1.0.0."""

    def export_spec(self, canvas_id: str) -> AgentSpec: ...


class Workflow(Protocol):
    """Platform Workflow SPI, interface_versions: 1.0.0."""

    def submit(self, spec: WorkflowSpec) -> WorkflowHandle: ...


class Sandbox(Protocol):
    """Platform Sandbox SPI, interface_versions: 1.0.0."""

    def execute(self, code: str, language: str) -> SandboxResult: ...


class CICD(Protocol):
    """Platform CICD SPI, interface_versions: 1.0.0."""

    def deploy(self, spec: DeploySpec) -> DeployHandle: ...


class MultiTenancy(Protocol):
    """Platform MultiTenancy SPI, interface_versions: 1.0.0."""

    def resolve_tenant(self, tenant_id: str) -> TenantConfig: ...


class MLOps(Protocol):
    """Platform MLOps SPI, interface_versions: 1.0.0."""

    def submit_fine_tune(self, spec: FineTuneSpec) -> FineTuneHandle: ...


class Eval(Protocol):
    """Platform Eval SPI, interface_versions: 1.0.0."""

    def run_eval(self, spec: EvalSpec) -> EvalReport: ...


__all__ = [
    "LLMProvider",
    "VectorStore",
    "AgentRuntime",
    "Cache",
    "Gateway",
    "Tracing",
    "Auth",
    "RAG",
    "LowCode",
    "Workflow",
    "Sandbox",
    "CICD",
    "MultiTenancy",
    "MLOps",
    "Eval",
]
