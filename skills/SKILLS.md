# ai-sdk-python · AI Coding Skills (SKILLS)

> **Source**: design/DESIGN.md §5 (Extension Points) · §4 (Key Usage and Code Examples) · §9 (Error Handling and Observability)
> **Audience**: AI coding Agent, SDK secondary developers
> **Collaboration**: arch/ARCH.md (architecture) · specs/SPECS.md (contract) · design/adr/ (decision record)
> **Platform version**: strata v1.4.0

---

## 1. Extension points (SPI port implementation guide)

> Corresponds to design/DESIGN.md §5. The extension point of the SDK is the platform SPI port; the name is consistent with the §10.4 canonical port name.
> The host application only needs to implement the corresponding `domain` protocol class and pass it into the constructor to replace the default implementation - **zero changes to the SDK core** (dependency inversion + anti-corrosion layer ACL).

### 1.1 Access custom LLMProvider

```python
from openstrata_sdk.domain import LLMProvider, ChatRequest, ChatResponse, EmbedRequest, EmbedResponse
from openstrata_sdk.domain import RerankRequest, RerankResponse, StreamChunk

class MySelfHosted:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def chat(self, req: ChatRequest) -> ChatResponse:
        #Tune your own vLLM/TGI OpenAI-compatible endpoint
        import httpx
        body = req.to_openai_compat()
        resp = httpx.post(f"{self.endpoint}/v1/chat/completions", json=body)
        resp.raise_for_status()
        return ChatResponse.model_validate(resp.json())

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        ...  #Ditto mode

    def rerank(self, req: RerankRequest) -> RerankResponse:
        ...

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]:
        #SSE streaming read → yield StreamChunk
        async with httpx.AsyncClient() as cli:
            async with cli.stream("POST", f"{self.endpoint}/v1/chat/completions", json=req.to_openai_compat()) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield StreamChunk.model_validate_json(line[6:])

# injection：replace default LLMProvider（full File self-hosting scenario, §4.4.2）
client = Client(llm_provider=MySelfHosted("http://vllm:8000"))
```

### 1.2 Access custom VectorStore / Cache

```python
from openstrata_sdk.domain import VectorStore, Doc, Hit

class MyChromaStore:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def upsert(self, collection: str, docs: list[Doc]) -> None:
        #Call ChromaDB API
        ...

    def search(self, collection: str, vec: list[float], top_k: int) -> list[Hit]:
        #ANN search
        return [Hit(id=..., score=..., content=...) ...]

    def delete(self, collection: str, ids: list[str]) -> None:
        ...

# injection
client = Client(
    vector_store=MyChromaStore("http://chroma:8000"),
    cache=MyCustomCache(),
)
```

Multiple implementations coexisting (Qdrant/Milvus, Redis/Valkey) are routed by the SDK factory according to `tenant.vector_store_preference` (§10.4 Runtime routing). Python protocol classes support structured subtyping without the need for explicit `class MyStore(VectorStore)`.

### 1.3 Access custom AgentRuntime / Tracing

```python
from openstrata_sdk.domain import AgentRuntime, AgentSpec, AgentHandle

class MyLocalRuntime:
    def __init__(self):
        self.graph = LocalGraph()

    def load(self, spec: AgentSpec) -> AgentHandle:
        #Parse AgentSpec → Build local execution graph
        compiled = self.graph.compile(spec)
        return AgentHandle(id=spec.metadata.name, payload=compiled)

    def run(self, handle: AgentHandle, input: dict) -> dict:
        #This map executes
        return handle.payload.execute(input)

client = Client(agent_runtime=MyLocalRuntime())
```

The SDK default implementation binds the platform LangGraph (Python) instance, but the host can change the local map executor without changing the spec - because AgentSpec is declarative and runtime independent (§4.3.5).

### 1.4 Complete list of SPI ports (strictly aligned with §10.4)

The SDK exposes all 15 types of port protocols:

| Port | Protocol Signature Summary | Version |
|------|-------------|------|
| `Gateway` | `invoke(req: GatewayRequest) -> GatewayResponse` | 1.2.0 |
| `AgentRuntime` | `load(spec) -> AgentHandle` / `run(handle, input) -> dict` | 1.3.0 |
| `LLMProvider` | `chat(...)` / `embed(...)` / `rerank(...)` / `stream(...)` → `AsyncIterator` | 1.0.0 |
| `VectorStore` | `upsert(...)` / `search(...)` / `delete(...)` | 1.1.0 |
| `Cache` | `get(key)` → `Optional[bytes]` / `set(key, val, ttl)` | 1.0.0 |
| `Auth` | `validate_token(token)` → `TenantContext` | 1.0.0 |
| `Tracing` | `start_span(name)` → `Span` | 1.0.0 |
| `RAG` | `retrieve(query, kb_id, top_k)` → `list[RAGHit]` | 1.0.0 |
| `LowCode` | `export_spec(canvas_id)` → `AgentSpec` | 1.0.0 |
| `Workflow` | `submit(spec)` → `WorkflowHandle` | 1.0.0 |
| `Sandbox` | `execute(code, language)` → `SandboxResult` | 1.0.0 |
| `CICD` | `deploy(spec)` → `DeployHandle` | 1.0.0 |
| `MultiTenancy` | `resolve_tenant(tenant_id)` → `TenantConfig` | 1.0.0 |
| `MLOps` | `submit_fine_tune(spec)` → `FineTuneHandle` | 1.0.0 |
| `Eval` | `run_eval(spec)` → `EvalReport` | 1.0.0 |

---

## 2. Key usage and code examples

> Corresponds to design/DESIGN.md §4. All examples run out of the box (Python 3.11+).

### 2.1 Quickstart: Run through conversational Agent in 30 minutes

```python
from openstrata_sdk import Client
from openstrata_sdk.domain import AgentSpec, ModelBinding, ObjectSchema, Guardrails

client = Client.from_env()

# declarative AgentSpec（§4.3.5 convergence contract）
spec = (
    AgentSpec.builder("customer-service-v2")
    .tenant("tenant-b")
    .model_binding(ModelBinding(
        preferred="cloud-qwen-max",
        fallback_chain=["local-qwen2.5-72b", "cloud-gpt-4o"]
    ))
    .input_schema(ObjectSchema("query", "string"))
    .output_schema(ObjectSchema("answer", "string"))
    .guardrails(Guardrails(basic=["injection_scan", "pii_scan", "rate_limit"]))
    .build()
)

# through AgentRuntime SPI Load and run（declarative、Runtime independent）
handle = client.agent_runtime.load(spec)
out = client.agent_runtime.run(handle, {"query": "Where's my order?"})
print(out["answer"])
```

### 2.2 Register Custom Tool

```python
from openstrata_sdk.domain import Tool

@Tool.register("order_lookup", input_schema=ObjectSchema("order_id", "string"))
def order_lookup(ctx, order_id: str) -> dict:
    #Adjust business database query
    return {"status": "shipped", "order_id": order_id}

# Method one：bind to AgentSpec
spec = spec.with_tool_bindings("order_lookup")

# Method 2：Register to the platform ToolRegistry（Walk Gateway SPI）
client.tools.register(order_lookup)

# Method three：use MCP protocol exposed
order_lookup.with_mcp(transport="stdio")
```

### 2.3 RAG retrieval

```python
# Get query vector（through LLMProvider embed）
emb = client.llm_provider.embed(EmbedRequest(texts=["Where's my order?"]))

# Search away VectorStore SPI；SDK Factory press tenant.vector_store_preference routing
hits = client.vector_store.search("kb-tenant-b", emb.vectors[0], top_k=5)

# Hit fragment backfill gives LLMProvider of prompt
for hit in hits:
    print(f"[{hit.id}] score={hit.score:.3f} chunk={hit.content}")
# RAG Pipelines are composed by platforms，SDK Only the retrieval port is exposed（§4.5）
```

### 2.4 Multi-round Session/Memory

```python
sess = client.session("user-123")
sess.set_working_memory_ttl(3600)  # working memory（§4.3.5 memory_bindings）

# first round：Setting memory
resp = client.chat(sess, "Remember my last name is Zhang, VIP level 5")

# second round：automatic injection memory_bindings context
resp = client.chat(sess, "What is my VIP level?")
print(resp)  #"You are VIP 5, Mr. Zhang"
```

### 2.5 Streaming call

```python
async for chunk in client.llm_provider.stream(
    ChatRequest(messages=[Message(role="user", content="write a poem")])
):
    print(chunk.delta, end="", flush=True)
print()
```

---

## 3. Error handling and observability → Coding rules

> Corresponds to design/DESIGN.md §9. The following rules are derived from the error model and observability design, and must be strictly implemented by the AI ​​coding agent.

### Rule R1: Use unified exception types

```python
class OpenStrataError(Exception):
    """SDK unified error types."""
    def __init__(self, port: str, code: str, retryable: bool, cause: Exception | None = None):
        self.port = port       #Error SPI port name
        self.code = code       #Platform error code (corresponding to Gateway response)
        self.retryable = retryable  #Is it possible to retry
        self.cause = cause
        super().__init__(f"[{port}] {code} retryable={retryable}: {cause}")
```

**Rule**: All SDK internal exceptions must be wrapped as `OpenStrataError`, marked `port` and `retryable`. Direct `raise e` is not allowed to pass through transparent exceptions.

### Rule R2: Do not retry by yourself, prompt the upper layer to use fallback_chain

```python
def chat(self, req: ChatRequest) -> ChatResponse:
    try:
        return self.provider.chat(req)
    except (TimeoutError, QuotaExceededError) as e:
        raise OpenStrataError(
            port="LLMProvider",
            code="LLM_TIMEOUT",
            retryable=True,
            cause=e,
        ) from e
        #Do not retry in this loop - the upper ModelRouter is responsible for failover
```

**Rule**: The SDK never does exponential backoff retries internally. Third-party LLM timeout/quota exceeded → `retryable=True` → thrown to the caller → `fallback_chain` (§4.4.5) taken by the platform ModelRouter. Avoid the SDK layer avalanche.

### Rule R3: All Port operations must be reported to Tracing span

```python
def _do_with_trace(self, port: str, fn):
    span = self._tracing.start_span(port)
    try:
        return fn()
    except OpenStrataError as e:
        span.set_status(StatusCode.ERROR, str(e))
        raise
    finally:
        span.end()
```

**Rule**: Each SPI port call must create a Tracing span (port name span name). On error, set span status to error and log `OpenStrataError` details.

### Rule R4: Audit log is enabled by default

```python
@dataclass
class AuditLog:
    timestamp: datetime
    tenant_id: str
    port: str
    operation: str
    latency: float
    error: str | None = None

def _emit_audit(self, log: AuditLog) -> None:
    if not self.config.observability.audit_log:
        return
    #The core baseline must enable auditing (§4.8), here only the switch is checked
    self._audit_writer.write(log)
```

**Rule**: All Gateway calls, AgentRuntime load/run, and Tool registration/execution must output audit logs. AgentSpec's `observability_hooks.audit: enabled` is the core baseline (§4.3.5).

### Rule R5: Metrics Hook reports key indicators

```python
@dataclass
class Metric:
    port: str
    operation: str
    token_usage: TokenUsage
    latency: float
    cache_hit_rate: float
    error_rate: float

# SDK exposed hook callback
client = Client(
    metrics_hook=lambda m: (
        #Exported via OTel exporter
        otel_metrics.record(m.port, m.token_usage, m.latency)
    ),
)
```

**Rules**: The `metrics_hook` callback is triggered after each SPI port call, including the four dimensions of token usage, call delay, cache hit rate, and error rate.

### Rule R6: Configure coverage priority

```
Construction parameters > environment variables > pyproject.toml [tool.openstrata] > platform Manifest
```

**Rule**: All configuration reads must be merged at this priority. `config.load()` is a unified entry that prohibits private reading of environment variables inside the adapter.

### Rule R7: Cross-language API semantic alignment

| Concepts | Python | Go | Java | Semantic Consistency |
|------|--------|-----|------|-----------|
| Error type | `OpenStrataError` | `domain.Error` | `OpenStrataException` | code + port + retryable |
| Streaming return | `AsyncIterator[StreamChunk]` | `<-chan StreamChunk` | `Flow<StreamChunk>` | Chunk-by-chunk push, 3 primitives are semantically equivalent |
| AgentSpec parsing | `AgentSpec.parse_yaml(yaml)` | `agent.ParseSpec(yaml)` | `AgentSpec.parse(yaml)` | The same YAML, isomorphic parsing |
| Configuration injection | Construction parameters | `client.WithXxx(...)` | `@Bean` coverage | Dependency inversion, implementation replacement without changing the core |

**Rule**: Method signature semantics for the same SPI port are consistent across languages. AgentSpec YAML schema and the three SDKs share the same fixture.

---

## 4. Coding rules cheat sheet

| Rule Number | One Sentence | Consequences of Violation |
|----------|--------|----------|
| R1 | All exceptions are packaged as `OpenStrataError` | The upper layer cannot determine retryability, and failover fails |
| R2 | No self-retry, throw `retryable=True` | Avalanche; ModelRouter fallback_chain is short-circuited |
| R3 | Each Port calls the package Tracing span | trace faults, unable to be traced end-to-end |
| R4 | Audit log is enabled by default | Compliance audit is missing (§4.8 core baseline) |
| R5 | Trigger MetricsHook | No token usage/latency/hit rate monitoring |
| R6 | Configuration coverage is merged according to priority | Configuration sources are confusing and debugging is difficult |
| R7 | Cross-language API semantic alignment | AgentSpec parsing is inconsistent in different SDKs |

---

> **Associated documents**: arch/ARCH.md (architecture and port list) · specs/SPECS.md (SPI version contract and configuration keys) · design/DESIGN.md (complete design)
