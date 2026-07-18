"""Pydantic v2 DTOs for the OpenStrata Python SDK (DESIGN §2.2 / §4).

These are value types only — no framework and no SPI dependency. They mirror
the value types of ai-sdk-java / ai-sdk-go for cross-language contract parity.

``ObjectSchema`` / ``ModelBinding`` / ``Guardrails`` live here (not in
``objects.py``) so the dependency points one way: ``objects`` -> ``models``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ObjectSchema:
    """JSON-Schema-ish descriptor for an Agent input/output field."""

    def __init__(
        self,
        name: str,
        type_: str,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.type = type_
        self.description = description
        self.properties = properties or {}

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "type": self.type}
        if self.description:
            d["description"] = self.description
        if self.properties:
            d["properties"] = self.properties
        return d


class ModelBinding:
    """Preferred model plus an ordered fallback chain (DESIGN §4.4.5)."""

    def __init__(self, preferred: str, fallback_chain: Optional[List[str]] = None) -> None:
        self.preferred = preferred
        self.fallback_chain = list(fallback_chain or [])


class Guardrails:
    """Safety checks applied at Agent runtime (DESIGN §4.3.5)."""

    def __init__(self, checks: Optional[List[str]] = None, basic: Optional[List[str]] = None) -> None:
        # Accept both spellings: `checks` (Go/Java parity) and `basic` (DESIGN example).
        self.checks = list(checks or basic or [])


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str
    name: Optional[str] = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    tenant: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = None
    model: Optional[str] = None
    content: str = ""
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    raw: Optional[Dict[str, Any]] = None


class EmbedRequest(BaseModel):
    inputs: List[str]
    model: Optional[str] = None


class EmbedResponse(BaseModel):
    model: Optional[str] = None
    vectors: List[List[float]] = Field(default_factory=list)


class RerankResult(BaseModel):
    index: int
    score: float
    doc: str


class RerankRequest(BaseModel):
    query: str
    docs: List[str]
    model: Optional[str] = None
    top_k: Optional[int] = None


class RerankResponse(BaseModel):
    model: Optional[str] = None
    results: List[RerankResult] = Field(default_factory=list)


class StreamChunk(BaseModel):
    delta: str = ""
    finish_reason: Optional[str] = None
    index: Optional[int] = None


class Doc(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    text: str
    vector: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


class Hit(BaseModel):
    id: str
    score: float
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RAGHit(BaseModel):
    id: str
    score: float
    text: str
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GatewayRequest(BaseModel):
    method: str = "POST"
    path: str
    body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    tenant: Optional[str] = None


class GatewayResponse(BaseModel):
    status: int = 200
    body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None


class Span(BaseModel):
    name: str
    ctx: Dict[str, Any] = Field(default_factory=dict)


class TenantContext(BaseModel):
    tenant_id: str
    roles: List[str] = Field(default_factory=list)
    attributes: Optional[Dict[str, Any]] = None


class TenantConfig(BaseModel):
    tenant_id: str
    vector_store_preference: Optional[str] = None
    cache_provider: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class AgentHandle(BaseModel):
    id: str
    spec_api_version: str = "openstrata.cc/v1"
    spec_kind: str = "AgentSpec"
    spec_metadata: Dict[str, Any] = Field(default_factory=dict)
    model: Optional[str] = None


class WorkflowSpec(BaseModel):
    name: str
    dag: Optional[Dict[str, Any]] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowHandle(BaseModel):
    id: str
    status: str = "submitted"


class SandboxResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    artifacts: Optional[Dict[str, Any]] = None


class DeploySpec(BaseModel):
    name: str
    image: Optional[str] = None
    replicas: Optional[int] = None


class DeployHandle(BaseModel):
    id: str
    url: Optional[str] = None
    status: str = "deploying"


class FineTuneSpec(BaseModel):
    base_model: str
    dataset: str
    hyperparameters: Optional[Dict[str, Any]] = None


class FineTuneHandle(BaseModel):
    id: str
    status: str = "queued"


class EvalSpec(BaseModel):
    name: str
    dataset: str
    criteria: Optional[Dict[str, Any]] = None


class EvalReport(BaseModel):
    score: float
    details: Optional[Dict[str, Any]] = None


class AgentSpec(BaseModel):
    """Declarative, runtime-independent Agent contract (DESIGN §4.3.5).

    Converges to ``apiVersion: openstrata.cc/v1``; identical in meaning across
    ai-sdk-go / ai-sdk-java / ai-sdk-python so the same spec can be built in any
    language and bound to any runtime.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    api_version: str = "openstrata.cc/v1"
    kind: str = "AgentSpec"
    tenant: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_binding: Optional[ModelBinding] = None
    tool_bindings: List[str] = Field(default_factory=list)
    memory_bindings: List[str] = Field(default_factory=list)
    state_machine: Optional[Dict[str, Any]] = None
    guardrails: Optional[Guardrails] = None
    input_schema: Optional[ObjectSchema] = None
    output_schema: Optional[ObjectSchema] = None

    @classmethod
    def builder(cls, name: str) -> "AgentSpecBuilder":
        return AgentSpecBuilder(name)


class AgentSpecBuilder:
    """Fluent builder for :class:`AgentSpec` (DESIGN §4.1)."""

    def __init__(self, name: str) -> None:
        self._spec = AgentSpec(metadata={"name": name})

    def tenant(self, tenant: str) -> "AgentSpecBuilder":
        self._spec.tenant = tenant
        return self

    def model_binding(self, mb: ModelBinding) -> "AgentSpecBuilder":
        self._spec.model_binding = mb
        return self

    def input_schema(self, schema: ObjectSchema) -> "AgentSpecBuilder":
        self._spec.input_schema = schema
        return self

    def output_schema(self, schema: ObjectSchema) -> "AgentSpecBuilder":
        self._spec.output_schema = schema
        return self

    def guardrails(self, g: Guardrails) -> "AgentSpecBuilder":
        self._spec.guardrails = g
        return self

    def tool_bindings(self, *names: str) -> "AgentSpecBuilder":
        self._spec.tool_bindings.extend(names)
        return self

    def with_tool_bindings(self, name: str) -> "AgentSpecBuilder":
        self._spec.tool_bindings.append(name)
        return self

    def memory_bindings(self, *names: str) -> "AgentSpecBuilder":
        self._spec.memory_bindings.extend(names)
        return self

    def state_machine(self, sm: Dict[str, Any]) -> "AgentSpecBuilder":
        self._spec.state_machine = sm
        return self

    def build(self) -> AgentSpec:
        return self._spec
