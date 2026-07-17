# ai-sdk-python · AI 编码技能（SKILLS）

> **来源**: design/DESIGN.md §5（扩展点）· §4（关键用法与代码示例）· §9（错误处理与可观测性）
> **受众**: AI 编码 Agent、SDK 二次开发者
> **协同**: arch/ARCH.md（架构）· specs/SPECS.md（契约）· design/adr/（决策记录）
> **平台版本**: strata v1.4.0

---

## 1. 扩展点（SPI 端口实现指南）

> 对应 design/DESIGN.md §5。 SDK 的扩展点即平台 SPI 端口；名称与 §10.4 canonical 端口名一致。
> 宿主应用只需实现对应 `domain` 协议类并传入构造器，即可替换默认实现——**零改动 SDK 核心**（依赖倒置 + 防腐层 ACL）。

### 1.1 接入自定义 LLMProvider

```python
from openstrata_sdk.domain import LLMProvider, ChatRequest, ChatResponse, EmbedRequest, EmbedResponse
from openstrata_sdk.domain import RerankRequest, RerankResponse, StreamChunk

class MySelfHosted:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def chat(self, req: ChatRequest) -> ChatResponse:
        # 调自有 vLLM/TGI OpenAI-compatible 端点
        import httpx
        body = req.to_openai_compat()
        resp = httpx.post(f"{self.endpoint}/v1/chat/completions", json=body)
        resp.raise_for_status()
        return ChatResponse.model_validate(resp.json())

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        ...  # 同上模式

    def rerank(self, req: RerankRequest) -> RerankResponse:
        ...

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]:
        # SSE 流式读取 → yield StreamChunk
        async with httpx.AsyncClient() as cli:
            async with cli.stream("POST", f"{self.endpoint}/v1/chat/completions", json=req.to_openai_compat()) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield StreamChunk.model_validate_json(line[6:])

# 注入：替换默认 LLMProvider（full 档自托管场景, §4.4.2）
client = Client(llm_provider=MySelfHosted("http://vllm:8000"))
```

### 1.2 接入自定义 VectorStore / Cache

```python
from openstrata_sdk.domain import VectorStore, Doc, Hit

class MyChromaStore:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def upsert(self, collection: str, docs: list[Doc]) -> None:
        # 调 ChromaDB API
        ...

    def search(self, collection: str, vec: list[float], top_k: int) -> list[Hit]:
        # ANN 检索
        return [Hit(id=..., score=..., content=...) ...]

    def delete(self, collection: str, ids: list[str]) -> None:
        ...

# 注入
client = Client(
    vector_store=MyChromaStore("http://chroma:8000"),
    cache=MyCustomCache(),
)
```

多实现并存（Qdrant/Milvus、Redis/Valkey）由 SDK 工厂按 `tenant.vector_store_preference` 路由（§10.4 运行时路由）。Python 协议类支持结构化子类型，无需显式 `class MyStore(VectorStore)`。

### 1.3 接入自定义 AgentRuntime / Tracing

```python
from openstrata_sdk.domain import AgentRuntime, AgentSpec, AgentHandle

class MyLocalRuntime:
    def __init__(self):
        self.graph = LocalGraph()

    def load(self, spec: AgentSpec) -> AgentHandle:
        # 解析 AgentSpec → 构建本地执行图
        compiled = self.graph.compile(spec)
        return AgentHandle(id=spec.metadata.name, payload=compiled)

    def run(self, handle: AgentHandle, input: dict) -> dict:
        # 本地图执行
        return handle.payload.execute(input)

client = Client(agent_runtime=MyLocalRuntime())
```

SDK 默认实现绑定平台 LangGraph（Python）实例，但宿主可换本地图执行器而不改 spec——因为 AgentSpec 声明式、与运行时无关（§4.3.5）。

### 1.4 SPI 端口完整清单（与 §10.4 严格对齐）

SDK 暴露全部 15 类端口协议：

| 端口 | 协议签名摘要 | 版本 |
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

## 2. 关键用法与代码示例

> 对应 design/DESIGN.md §4。所有示例可直接运行（Python 3.11+）。

### 2.1 Quickstart: 30 分钟跑通对话式 Agent

```python
from openstrata_sdk import Client
from openstrata_sdk.domain import AgentSpec, ModelBinding, ObjectSchema, Guardrails

client = Client.from_env()

# 声明式 AgentSpec（§4.3.5 收敛契约）
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

# 经 AgentRuntime SPI 加载并运行（声明式、与运行时无关）
handle = client.agent_runtime.load(spec)
out = client.agent_runtime.run(handle, {"query": "我的订单到哪了？"})
print(out["answer"])
```

### 2.2 注册自定义 Tool

```python
from openstrata_sdk.domain import Tool

@Tool.register("order_lookup", input_schema=ObjectSchema("order_id", "string"))
def order_lookup(ctx, order_id: str) -> dict:
    # 调业务数据库查询
    return {"status": "shipped", "order_id": order_id}

# 方式一：绑定到 AgentSpec
spec = spec.with_tool_bindings("order_lookup")

# 方式二：注册到平台 ToolRegistry（走 Gateway SPI）
client.tools.register(order_lookup)

# 方式三：使用 MCP 协议暴露
order_lookup.with_mcp(transport="stdio")
```

### 2.3 RAG 检索

```python
# 获取查询向量（经 LLMProvider embed）
emb = client.llm_provider.embed(EmbedRequest(texts=["我的订单到哪了？"]))

# 检索走 VectorStore SPI；SDK 工厂按 tenant.vector_store_preference 路由
hits = client.vector_store.search("kb-tenant-b", emb.vectors[0], top_k=5)

# 命中片段回填给 LLMProvider 的 prompt
for hit in hits:
    print(f"[{hit.id}] score={hit.score:.3f} chunk={hit.content}")
# RAG 管线由平台组合，SDK 仅暴露检索端口（§4.5）
```

### 2.4 多轮 Session / 记忆

```python
sess = client.session("user-123")
sess.set_working_memory_ttl(3600)  # working memory（§4.3.5 memory_bindings）

# 首轮：设置记忆
resp = client.chat(sess, "记住我姓张，VIP 等级 5")

# 次轮：自动注入 memory_bindings 上下文
resp = client.chat(sess, "我的 VIP 等级是多少？")
print(resp)  # "您是 VIP 5，张先生"
```

### 2.5 流式调用

```python
async for chunk in client.llm_provider.stream(
    ChatRequest(messages=[Message(role="user", content="写一首诗")])
):
    print(chunk.delta, end="", flush=True)
print()
```

---

## 3. 错误处理与可观测性 → 编码规则

> 对应 design/DESIGN.md §9。以下规则由错误模型和可观测性设计推导，AI 编码 Agent 须严格执行。

### 规则 R1: 使用统一异常类型

```python
class OpenStrataError(Exception):
    """SDK 统一错误类型。"""
    def __init__(self, port: str, code: str, retryable: bool, cause: Exception | None = None):
        self.port = port       # 出错 SPI 端口名
        self.code = code       # 平台错误码（对应 Gateway 响应）
        self.retryable = retryable  # 是否可重试
        self.cause = cause
        super().__init__(f"[{port}] {code} retryable={retryable}: {cause}")
```

**规则**: 所有 SDK 内部异常必须包装为 `OpenStrataError`，标注 `port` 和 `retryable`。不允许直接 `raise e` 穿透明细异常。

### 规则 R2: 不自行重试，提示上层走 fallback_chain

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
        # 不在此循环重试 —— 上层 ModelRouter 负责故障转移
```

**规则**: SDK 永远不在内部做指数退避重试。第三方 LLM 超时/配额超限 → `retryable=True` → 抛出给调用方 → 由平台 ModelRouter 走 `fallback_chain`（§4.4.5）。避免 SDK 层雪崩。

### 规则 R3: 所有 Port 操作须上报 Tracing span

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

**规则**: 每个 SPI 端口调用必须创建一个 Tracing span（端口名作 span name）。出错时设置 span 状态为 error 并记录 `OpenStrataError` 详情。

### 规则 R4: 审计日志默认开启

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
    # core 基线必须开启审计（§4.8），这里仅检查开关
    self._audit_writer.write(log)
```

**规则**: 所有 Gateway 调用、AgentRuntime load/run、Tool 注册/执行必须输出审计日志。AgentSpec 的 `observability_hooks.audit: enabled` 为 core 基线（§4.3.5）。

### 规则 R5: Metrics Hook 上报关键指标

```python
@dataclass
class Metric:
    port: str
    operation: str
    token_usage: TokenUsage
    latency: float
    cache_hit_rate: float
    error_rate: float

# SDK 暴露 hook 回调
client = Client(
    metrics_hook=lambda m: (
        # 经 OTel exporter 导出
        otel_metrics.record(m.port, m.token_usage, m.latency)
    ),
)
```

**规则**: 每个 SPI 端口调用结束后触发 `metrics_hook` 回调，包含 token 用量、调用延迟、缓存命中率、错误率四个维度。

### 规则 R6: 配置覆盖优先级

```
构造参数 > 环境变量 > pyproject.toml [tool.openstrata] > 平台 Manifest
```

**规则**: 所有配置读取必须按此优先级合并。`config.load()` 统一入口，禁止在 adapter 内部私读环境变量。

### 规则 R7: 跨语言 API 语义对齐

| 概念 | Python | Go | Java | 语义一致性 |
|------|--------|-----|------|-----------|
| 错误类型 | `OpenStrataError` | `domain.Error` | `OpenStrataException` | code + port + retryable |
| 流式返回 | `AsyncIterator[StreamChunk]` | `<-chan StreamChunk` | `Flow<StreamChunk>` | 逐块推送，3 种原语语义等价 |
| AgentSpec 解析 | `AgentSpec.parse_yaml(yaml)` | `agent.ParseSpec(yaml)` | `AgentSpec.parse(yaml)` | 同一份 YAML，同构解析 |
| 配置注入 | 构造参数 | `client.WithXxx(...)` | `@Bean` 覆盖 | 依赖倒置，实现替换不改核心 |

**规则**: 同一 SPI 端口的方法签名语义跨语言一致。AgentSpec YAML schema 三 SDK 共用同一份 fixture。

---

## 4. 编码规则速查表

| 规则编号 | 一句话 | 违反后果 |
|----------|--------|----------|
| R1 | 所有异常包装为 `OpenStrataError` | 上层无法判断可重试性，故障转移失效 |
| R2 | 不自重试，抛 `retryable=True` | 雪崩；ModelRouter fallback_chain 被短路 |
| R3 | 每个 Port 调用包裹 Tracing span | trace 断层，无法端到端追踪 |
| R4 | 审计日志默认开 | 合规审计缺失（§4.8 core 基线） |
| R5 | 触发 MetricsHook | 无 token 用量/延迟/命中率监控 |
| R6 | 配置覆盖按优先级合并 | 配置源混乱，调试困难 |
| R7 | 跨语言 API 语义对齐 | AgentSpec 在不同 SDK 解析不一致 |

---

> **关联文档**: arch/ARCH.md（架构与端口清单）· specs/SPECS.md（SPI 版本契约与配置键）· design/DESIGN.md（完整设计）
