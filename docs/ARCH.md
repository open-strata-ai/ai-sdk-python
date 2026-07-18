# ai-sdk-python · Architecture (ARCH)

> **Source**: docs/DESIGN.md §1 (Positioning) · §2 (Core Abstraction) · §6 (SPI Mapping 15 Port)
> **Audience**: Platform architects, SDK maintainers, AI coding agents
> **Collaboration**: docs/SKILLS.md (extension points and coding rules) · docs/SPECS.md (contracts and versions) · docs/adr/ (major decisions)
> **Platform version**: strata v1.0.0

---

## 1. Positioning and target users

### 1.1 What is SDK

`ai-sdk-python` is the official developer library of the OpenStrata platform for the **Python ecosystem**, published to PyPI (`pip install openstrata-sdk`, import `openstrata_sdk`). It is a three-layer lightweight library of "client + builder + extension port", and is not a deployable service.

Core Commitments:
- **Pythonic**: fluent builder, dataclass, async/await, Pydantic v2 type safety
- **Minimal Invasion**: Only relies on Python 3.11+ + pydantic v2 + httpx + very few necessary dependencies (`opentelemetry-api`), and can be embedded in any Python host
- **Declarative AgentSpec**: Agent behavior converges to `apiVersion: openstrata.cc/v1` AgentSpec, language/runtime independent (§4.3.5)
- **Dependency Inversion**: All platform SPIs are exposed with the `openstrata_sdk.domain` protocol class, and there is no change to the SDK core when the host injects custom adapters

### 1.2 What problem is solved?

Let Python developers work Pythonic with existing Python applications (FastAPI services, notebooks, scripts, AI/ML pipelines):
1. Build a conversational Agent/Client and access platform runtime capabilities (gateway, Agent runtime, tool registration, memory, RAG, cache, observable)
2. Encapsulate internal capabilities into platform tools and connect business data to RAG
3. Implement customized `LLMProvider`/`VectorStore`/`Cache`/`AgentRuntime` adapter based on SDK’s SPI port

### 1.3 Target user portrait

| Character | Scene | Contact |
|------|------|--------|
| Python/AI Engineer | Embed Agent in existing FastAPI/Script | `Client`, `AgentSpec` |
| Platform secondary developer | Implement custom SPI Adapter | `openstrata_sdk.domain` protocol class |
| AI Coding Agent | Generate adaptation code according to skills/ rules | docs/SKILLS.md |

### 1.4 Boundary with platform

```
Python Host ──→ openstrata_sdk ──→ OpenStrata platform SPI
  (Already)           (Main repository)             (Gateway wait)
```

- SDK only relies on Python 3.11+ + pydantic v2 + httpx + very few necessary dependencies (§15.5.1 Framework Convergence)
- SDK manages dependencies through Poetry, `pyproject.toml` declaration
- SDK does not hold third-party Provider Key; the key is routed indirectly via the platform Secret Vault + Gateway (§4.4.6)

---

## 2. Core abstraction

### 2.1 Package structure (DDD four layers)

```
ai-sdk-python/
├── app/                            #Optional demo (non-publishing subject)
└── src/openstrata_sdk/
    ├── api/                        #① Access layer: Client, DTO (Pydantic v2)
    ├── application/                #② Application layer: Agent orchestration use cases
    ├── domain/                     #③ Domain layer: AgentSpec/Tool/Session entity + Port(Protocol)
    ├── infrastructure/             #④ Infrastructure layer: SPI Adapter (LLMProvider/VectorStore/Cache…)
    └── config.py                   #Configuration loading (infrastructure/config fragment rendering)
└── pyproject.toml                  #Poetry dependencies and packaging
```

Hierarchical dependency: ①→②→③←④. The domain layer (③) does not depend on any framework/external components, and the dependence direction points from ①② inward to ③.

### 2.2 First-class citizen objects (5 external objects)

| Abstract | Import path | Corresponding platform SPI | Description |
|------|----------|-------------|------|
| `Client` | `openstrata_sdk.api` | **Gateway** SPI (§4.4.1) | OpenAI-compatible call entry; holds tenant Token |
| `Agent` / `AgentSpec` | `openstrata_sdk.application` | **AgentRuntime** SPI (§4.3.5) | Declarative assembly AgentSpec (apiVersion/kind/metadata/model_binding/tool_bindings/memory_bindings/state_machine/guardrails) |
| `Tool` | `openstrata_sdk.domain` | **ToolRegistry** (§4.3.2) | Declare JSON Schema, support MCP stdio/SSE/HTTP |
| `Session` | `openstrata_sdk.domain` | **Cache** SPI (§4.3.4) | Multi-round session/memory handle, binding memory_bindings |
| `Retriever` | `openstrata_sdk.domain` | **VectorStore** SPI (§10.4) + **RAG** ​​SPI | Knowledge base retrieval, return hit fragments |

### 2.3 Domain layer Port protocol (dependency inversion)

The domain layer defines the following SPI port protocol (`typing.Protocol`) in `openstrata_sdk.domain`, and the name is strictly consistent with the platform §10.4 canonical port name**:

```python
from typing import Protocol, AsyncIterator, Optional, List
from openstrata_sdk.domain.models import (
    ChatRequest, ChatResponse, EmbedRequest, EmbedResponse,
    RerankRequest, RerankResponse, StreamChunk, Doc, Hit,
    AgentSpec, AgentHandle, GatewayRequest, GatewayResponse,
    Span, TenantContext, RAGHit, WorkflowSpec, WorkflowHandle,
    SandboxResult, DeploySpec, DeployHandle, TenantConfig,
    FineTuneSpec, FineTuneHandle, EvalSpec, EvalReport,
)

# LLMProvider —— Corresponding platform LLMProvider SPI（§4.4.4），interface_versions: 1.0.0
class LLMProvider(Protocol):
    def chat(self, req: ChatRequest) -> ChatResponse: ...
    def embed(self, req: EmbedRequest) -> EmbedResponse: ...
    def rerank(self, req: RerankRequest) -> RerankResponse: ...
    def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]: ...

# VectorStore —— Corresponding platform VectorStore SPI（§10.4），interface_versions: 1.0.0
class VectorStore(Protocol):
    def upsert(self, collection: str, docs: list[Doc]) -> None: ...
    def search(self, collection: str, vec: list[float], top_k: int) -> list[Hit]: ...
    def delete(self, collection: str, ids: list[str]) -> None: ...

# AgentRuntime —— Corresponding platform AgentRuntime SPI（§10.6 / §4.3.5），interface_versions: 1.0.0
class AgentRuntime(Protocol):
    def load(self, spec: AgentSpec) -> AgentHandle: ...
    def run(self, handle: AgentHandle, input: dict) -> dict: ...

# Cache —— Corresponding platform Cache SPI（§4.3.4），interface_versions: 1.0.0
class Cache(Protocol):
    def get(self, key: str) -> Optional[bytes]: ...
    def set(self, key: str, val: bytes, ttl: float) -> None: ...

# Gateway —— Corresponding platform Gateway SPI（§4.4.1），interface_versions: 1.0.0
class Gateway(Protocol):
    def invoke(self, req: GatewayRequest) -> GatewayResponse: ...

# Tracing —— Corresponding platform Tracing SPI（§4.8），interface_versions: 1.0.0
class Tracing(Protocol):
    def start_span(self, name: str) -> Span: ...

# Auth —— Corresponding platform Auth SPI，interface_versions: 1.0.0
class Auth(Protocol):
    def validate_token(self, token: str) -> TenantContext: ...

# RAG —— Corresponding platform RAG SPI，interface_versions: 1.0.0
class RAG(Protocol):
    def retrieve(self, query: str, kb_id: str, top_k: int) -> list[RAGHit]: ...

# LowCode —— Corresponding platform LowCode SPI，interface_versions: 1.0.0
class LowCode(Protocol):
    def export_spec(self, canvas_id: str) -> AgentSpec: ...

# Workflow —— Corresponding platform Workflow SPI，interface_versions: 1.0.0
class Workflow(Protocol):
    def submit(self, spec: WorkflowSpec) -> WorkflowHandle: ...

# Sandbox —— Corresponding platform Sandbox SPI，interface_versions: 1.0.0
class Sandbox(Protocol):
    def execute(self, code: str, language: str) -> SandboxResult: ...

# CICD —— Corresponding platform CICD SPI，interface_versions: 1.0.0
class CICD(Protocol):
    def deploy(self, spec: DeploySpec) -> DeployHandle: ...

# MultiTenancy —— Corresponding platform MultiTenancy SPI，interface_versions: 1.0.0
class MultiTenancy(Protocol):
    def resolve_tenant(self, tenant_id: str) -> TenantConfig: ...

# MLOps —— Corresponding platform MLOps SPI，interface_versions: 1.0.0
class MLOps(Protocol):
    def submit_fine_tune(self, spec: FineTuneSpec) -> FineTuneHandle: ...

# Eval —— Corresponding platform Eval SPI，interface_versions: 1.0.0
class Eval(Protocol):
    def run_eval(self, spec: EvalSpec) -> EvalReport: ...
```

> **Key Agreement**: All port protocols do not contain any specific framework/external component dependencies (§15.5.2 Domain Layer Prohibition). Method signatures are semantically consistent with the Go/Java SDK (cross-language contract).

### 2.4 Assembly model

The SDK uses constructor injection mode:

```python
# Method one：from_env Quick assembly（recommend，Production）
from openstrata_sdk import Client
client = Client.from_env()

# Method 2：Construct parameter injection into custom implementation（Secondary development）
from openstrata_sdk import Client
from openstrata_sdk.infrastructure import HigressGateway, QwenProvider, RedisCache

client = Client(
    gateway=HigressGateway.from_env(),
    llm_provider=QwenProvider.from_env(),
    cache=RedisCache.from_env(),
)

# Method three：Replace with custom implementation
client = Client(
    llm_provider=MySelfHosted("http://vllm:8000"),
    vector_store=MyChromaStore("http://chroma:8000"),
)
```

---

## 3. Mapping with platform SPI (15 port→canonical→interface_versions)

> Corresponds to docs/DESIGN.md §6, strictly aligned with Platform §10.4.

### 3.1 Mapping table

| SDK domain port (domain) | Platform SPI port (§10.4 canonical) | interface_versions | SDK role | Default Adapter (bom.yaml) |
| --- | --- | --- | --- | --- |
| `Gateway` | **Gateway** | 1.0.0 | Production(invoke) | Higress(core) |
| `AgentRuntime` | **AgentRuntime** | 1.0.0 | Production (Load/Run) | LangGraph binding execution (core) |
| `LLMProvider` | **LLMProvider** | 1.0.0 | Production (chat/embed/rerank/stream) | Qwen-Cloud / OpenAI / Claude (core third party) |
| `VectorStore` | **VectorStore** | 1.0.0 | Production (upsert/search/delete) | Qdrant (core)/Milvus (optional) |
| `Cache` | **Cache** | 1.0.0 | Production (semantic/accurate caching) | Redis (core)/Valkey (optional, OSI) |
| `Auth` | **Auth** | 1.0.0 | Consumption (tenant Token verification) | Keycloak (core) |
| `Tracing` | **Tracing** | 1.0.0 | Production (span) | Langfuse (core) / OTel (core baseline) |
| `RAG` | **RAG** ​​| 1.0.0 | Consumption (retrieval backfill) | RAGFlow (core) |
| `LowCode` | **LowCode** | 1.0.0 | Consumption (canvas→AgentSpec) | Self-developed React Flow (core)/Dify (reference) |
| `Workflow` | **Workflow** | 1.0.0 | Consumption (long task orchestration) | Temporal (optional) |
| `Sandbox` | **Sandbox** | 1.0.0 | Consumption (code execution isolation) | Kata / E2B (optional) |
| `CICD` | **CICD** | 1.0.0 | Consumption (canary Release) | ArgoCD/Istio (optional) |
| `MultiTenancy` | **MultiTenancy** | 1.0.0 | Consumption (Tenant Isolation Context) | Capsule (optional) |
| `MLOps` | **MLOps** | 1.0.0 | Consume (fine-tuning/distillation) | MLflow (optional) |
| `Eval` | **Eval** | 1.0.0 | Consumption (evaluation reflow) | Promptfoo / DeepEval / Ragas (core/optional) |

### 3.2 Role classification

| SDK role | Meaning | Ports involved |
|----------|------|----------|
| **Producer** | SDK actively calls platform services, generates data or performs operations | Gateway, AgentRuntime, LLMProvider, VectorStore, Cache, Tracing |
| **Consumer** | The context/configuration issued by the SDK consumer platform and not actively modified | Auth, RAG, LowCode, Workflow, Sandbox, CICD, MultiTenancy, MLOps, Eval |

### 3.3 Key constraints

1. **The port name is word-for-word**: The SDK port name is exactly the same as the `bom.yaml` `spi` field (§16.2); new/replacement implementations never need to change the core (§10.6 Registry model)
2. **Same-level failover**: Self-hosting and multiple third-party implementations coexist behind the same `LLMProvider` SPI. Cross-implementation failover is handled by the platform `ModelRouter` (§4.4.4/§4.4.5)
3. **VectorStore silent switching**: When switching the VectorStore provider, the platform migrates the Job double-write verification (§10.4), the SDK obtains the corresponding Adapter through the SPI factory, and the application code is zero-changed
4. **Configuration override priority**: Construction parameters > Environment variables > `pyproject.toml` `[tool.openstrata]` > Platform Manifest delivery (§12)

### 3.4 Relationship between ports (data flow)

```
Gateway ──→ LLMProvider ──→ (chat/embed/rerank/stream)
Gateway ──→ VectorStore ──→ RAG ──→ (Search backfill prompt)
Gateway ──→ Cache ──→ Session ──→ (session memory)
AgentRuntime ──→ Tracing ──→ (span Report)
Gateway ──→ Auth ──→ MultiTenancy ──→ (Tenant context)
Workflow ──→ Sandbox ──→ (Long task code isolation)
MLOps ──→ Eval ──→ LowCode ──→ (fine-tuning→Review→Canvas export)
```

### 3.5 Python-specific constraints

- All Port protocols use `typing.Protocol` (structured subtyping, no explicit inheritance required)
- `stream()` returns `AsyncIterator[StreamChunk]` (Python async/await primitive)
- `Cache.get()` returns `Optional[bytes]` to explicitly indicate a cache miss
- Injection via `Client(...)` constructor parameter
- Compatible with both `async` and synchronous calling contexts; the default implementation supports `from_env()` functional simplification

---

> **Associated documents**: docs/SKILLS.md (extension points and coding rules) · docs/SPECS.md (SPI version contract and configuration keys) · docs/DESIGN.md (complete design)
