"""OpenStrata Python SDK (``openstrata_sdk``).

A three-layer "client + builder + extension port" developer library for the
OpenStrata platform. It mirrors ai-sdk-java / ai-sdk-go: 15 SPI ports + 5
first-class objects, with dependency inversion (hosts inject their own SPI
adapters; the SDK core never changes).

Quickstart::

    from openstrata_sdk import Client
    client = Client.from_env()

    spec = (AgentSpec.builder("customer-service-v2")
            .tenant("tenant-b")
            .model_binding(ModelBinding(preferred="cloud-qwen-max"))
            .input_schema(ObjectSchema("query", "string"))
            .output_schema(ObjectSchema("answer", "string"))
            .guardrails(Guardrails(checks=["injection_scan", "pii_scan"]))
            .build())

    handle = client.agent_runtime.load(spec)
    out = client.agent_runtime.run(handle, {"query": "Where is my order?"})
"""

from openstrata_sdk.api.client import Client
from openstrata_sdk.application.agent import Agent, AgentSpec
from openstrata_sdk.domain.models import (
    AgentHandle,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Doc,
    EmbedRequest,
    EmbedResponse,
    EvalReport,
    EvalSpec,
    GatewayRequest,
    GatewayResponse,
    Hit,
    RAGHit,
    RerankRequest,
    RerankResponse,
    Span,
    StreamChunk,
    TenantConfig,
    TenantContext,
)
from openstrata_sdk.domain import (
    Guardrails,
    ModelBinding,
    ObjectSchema,
    OpenStrataError,
    Retriever,
    Session,
    Tool,
)
from openstrata_sdk.domain.ports import (
    AgentRuntime,
    Auth,
    CICD,
    Cache,
    Eval,
    Gateway,
    LLMProvider,
    LowCode,
    MLOps,
    MultiTenancy,
    RAG,
    Sandbox,
    Tracing,
    VectorStore,
    Workflow,
)

__version__ = "1.0.0"

__all__ = [
    "Client", "Agent", "AgentSpec", "AgentHandle",
    "ChatRequest", "ChatResponse", "ChatMessage", "EmbedRequest", "EmbedResponse",
    "RerankRequest", "RerankResponse", "StreamChunk", "Doc", "Hit", "RAGHit",
    "GatewayRequest", "GatewayResponse", "Span", "TenantContext", "TenantConfig",
    "EvalSpec", "EvalReport",
    "Tool", "Session", "Retriever", "ObjectSchema", "ModelBinding", "Guardrails",
    "OpenStrataError",
    "LLMProvider", "VectorStore", "AgentRuntime", "Cache", "Gateway", "Tracing",
    "Auth", "RAG", "LowCode", "Workflow", "Sandbox", "CICD", "MultiTenancy",
    "MLOps", "Eval",
]
