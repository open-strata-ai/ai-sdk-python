# ai-sdk-python · 架构（ARCH）

> **来源**: design/DESIGN.md §1（定位）· §2（核心抽象）· §6（SPI 映射 15 端口）
> **受众**: 平台架构师、SDK 维护者、AI 编码 Agent
> **协同**: skills/SKILLS.md（扩展点与编码规则）· specs/SPECS.md（契约与版本）· design/adr/（重大决策）
> **平台版本**: strata v1.4.0

---

## 1. 定位与目标用户

### 1.1 SDK 是什么

`ai-sdk-python` 是 OpenStrata 平台面向 **Python 生态**的官方开发者库，发布到 PyPI（`pip install openstrata-sdk`，import `openstrata_sdk`）。它是"客户端 + 构建器 + 扩展端口"三层合一的轻量库，不是可部署服务。

核心承诺：
- **Pythonic**: fluent builder、dataclass、async/await、Pydantic v2 类型安全
- **最小侵入**: 仅依赖 Python 3.11+ + pydantic v2 + httpx + 极少量必要依赖（`opentelemetry-api`），可嵌入任意 Python 宿主
- **声明式 AgentSpec**: Agent 行为收敛为 `apiVersion: openstrata.io/v1` AgentSpec，与语言/运行时无关（§4.3.5）
- **依赖倒置**: 所有平台 SPI 以 `openstrata_sdk.domain` 协议类暴露，宿主注入自定义适配器时零改动 SDK 核心

### 1.2 解决什么问题

让 Python 开发者在已有 Python 应用（FastAPI 服务、Notebook、脚本、AI/ML 管线）中以 Pythonic 方式：
1. 构建对话式 Agent/Client，接入平台运行时能力（网关、Agent 运行时、工具注册、记忆、RAG、缓存、可观测）
2. 把内部能力封装成平台 Tool，将业务数据接入 RAG
3. 基于 SDK 的 SPI 端口实现自定义 `LLMProvider`/`VectorStore`/`Cache`/`AgentRuntime` 适配器

### 1.3 目标用户画像

| 角色 | 场景 | 接触面 |
|------|------|--------|
| Python/AI 工程师 | 在现有 FastAPI/脚本中嵌入 Agent | `Client`、`AgentSpec` |
| 平台二次开发者 | 实现自定义 SPI Adapter | `openstrata_sdk.domain` 协议类 |
| AI 编码 Agent | 按 skills/ 规则生成适配代码 | skills/SKILLS.md |

### 1.4 与平台的边界

```
Python 宿主 ──→ openstrata_sdk ──→ OpenStrata 平台 SPI
  (已有)           (本仓)             (Gateway 等)
```

- SDK 仅依赖 Python 3.11+ + pydantic v2 + httpx + 极少量必要依赖（§15.6.1 框架收敛）
- SDK 通过 Poetry 管理依赖，`pyproject.toml` 声明
- SDK 不持有第三方 Provider Key；密钥经平台 Secret Vault + Gateway 间接路由（§4.4.6）

---

## 2. 核心抽象

### 2.1 包结构（DDD 四层）

```
ai-sdk-python/
├── app/                            # 可选 demo（非发布主体）
└── src/openstrata_sdk/
    ├── api/                        # ① 接入层：Client、DTO（Pydantic v2）
    ├── application/                # ② 应用层：Agent 编排用例
    ├── domain/                     # ③ 领域层：AgentSpec/Tool/Session 实体 + Port(Protocol)
    ├── infrastructure/             # ④ 基础设施层：SPI Adapter（LLMProvider/VectorStore/Cache…）
    └── config.py                   # 配置加载（infrastructure/config 片段渲染）
└── pyproject.toml                  # Poetry 依赖与打包
```

层次依赖：①→②→③←④。领域层（③）不依赖任何框架/外部组件，依赖方向自 ①② 向内指向 ③。

### 2.2 一等公民对象（5 个对外对象）

| 抽象 | 导入路径 | 对应平台 SPI | 说明 |
|------|----------|-------------|------|
| `Client` | `openstrata_sdk.api` | **Gateway** SPI (§4.4.1) | OpenAI-compatible 调用入口；持有租户 Token |
| `Agent` / `AgentSpec` | `openstrata_sdk.application` | **AgentRuntime** SPI (§4.3.5) | 声明式拼装 AgentSpec（apiVersion/kind/metadata/model_binding/tool_bindings/memory_bindings/state_machine/guardrails） |
| `Tool` | `openstrata_sdk.domain` | **ToolRegistry** (§4.3.2) | 声明 JSON Schema，支持 MCP stdio/SSE/HTTP |
| `Session` | `openstrata_sdk.domain` | **Cache** SPI (§4.3.4) | 多轮会话/记忆句柄，绑定 memory_bindings |
| `Retriever` | `openstrata_sdk.domain` | **VectorStore** SPI (§10.4) + **RAG** SPI | 知识库检索，返回命中片段 |

### 2.3 领域层 Port 协议（依赖倒置）

领域层在 `openstrata_sdk.domain` 中定义以下 SPI 端口协议（`typing.Protocol`），名称与平台 §10.4 canonical 端口名**严格一致**：

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

# LLMProvider —— 对应平台 LLMProvider SPI（§4.4.4），interface_versions: 1.0.0
class LLMProvider(Protocol):
    def chat(self, req: ChatRequest) -> ChatResponse: ...
    def embed(self, req: EmbedRequest) -> EmbedResponse: ...
    def rerank(self, req: RerankRequest) -> RerankResponse: ...
    def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]: ...

# VectorStore —— 对应平台 VectorStore SPI（§10.4），interface_versions: 1.1.0
class VectorStore(Protocol):
    def upsert(self, collection: str, docs: list[Doc]) -> None: ...
    def search(self, collection: str, vec: list[float], top_k: int) -> list[Hit]: ...
    def delete(self, collection: str, ids: list[str]) -> None: ...

# AgentRuntime —— 对应平台 AgentRuntime SPI（§10.6 / §4.3.5），interface_versions: 1.3.0
class AgentRuntime(Protocol):
    def load(self, spec: AgentSpec) -> AgentHandle: ...
    def run(self, handle: AgentHandle, input: dict) -> dict: ...

# Cache —— 对应平台 Cache SPI（§4.3.4），interface_versions: 1.0.0
class Cache(Protocol):
    def get(self, key: str) -> Optional[bytes]: ...
    def set(self, key: str, val: bytes, ttl: float) -> None: ...

# Gateway —— 对应平台 Gateway SPI（§4.4.1），interface_versions: 1.2.0
class Gateway(Protocol):
    def invoke(self, req: GatewayRequest) -> GatewayResponse: ...

# Tracing —— 对应平台 Tracing SPI（§4.8），interface_versions: 1.0.0
class Tracing(Protocol):
    def start_span(self, name: str) -> Span: ...

# Auth —— 对应平台 Auth SPI，interface_versions: 1.0.0
class Auth(Protocol):
    def validate_token(self, token: str) -> TenantContext: ...

# RAG —— 对应平台 RAG SPI，interface_versions: 1.0.0
class RAG(Protocol):
    def retrieve(self, query: str, kb_id: str, top_k: int) -> list[RAGHit]: ...

# LowCode —— 对应平台 LowCode SPI，interface_versions: 1.0.0
class LowCode(Protocol):
    def export_spec(self, canvas_id: str) -> AgentSpec: ...

# Workflow —— 对应平台 Workflow SPI，interface_versions: 1.0.0
class Workflow(Protocol):
    def submit(self, spec: WorkflowSpec) -> WorkflowHandle: ...

# Sandbox —— 对应平台 Sandbox SPI，interface_versions: 1.0.0
class Sandbox(Protocol):
    def execute(self, code: str, language: str) -> SandboxResult: ...

# CICD —— 对应平台 CICD SPI，interface_versions: 1.0.0
class CICD(Protocol):
    def deploy(self, spec: DeploySpec) -> DeployHandle: ...

# MultiTenancy —— 对应平台 MultiTenancy SPI，interface_versions: 1.0.0
class MultiTenancy(Protocol):
    def resolve_tenant(self, tenant_id: str) -> TenantConfig: ...

# MLOps —— 对应平台 MLOps SPI，interface_versions: 1.0.0
class MLOps(Protocol):
    def submit_fine_tune(self, spec: FineTuneSpec) -> FineTuneHandle: ...

# Eval —— 对应平台 Eval SPI，interface_versions: 1.0.0
class Eval(Protocol):
    def run_eval(self, spec: EvalSpec) -> EvalReport: ...
```

> **关键约定**: 所有端口协议不含任何具体框架/外部组件依赖（§15.6.2 领域层禁令）。方法签名与 Go/Java SDK 语义一致（跨语言契约）。

### 2.4 装配模型

SDK 采用构造注入模式：

```python
# 方式一：from_env 快速装配（推荐，生产）
from openstrata_sdk import Client
client = Client.from_env()

# 方式二：构造参数注入自定义实现（二次开发）
from openstrata_sdk import Client
from openstrata_sdk.infrastructure import HigressGateway, QwenProvider, RedisCache

client = Client(
    gateway=HigressGateway.from_env(),
    llm_provider=QwenProvider.from_env(),
    cache=RedisCache.from_env(),
)

# 方式三：替换为自定义实现
client = Client(
    llm_provider=MySelfHosted("http://vllm:8000"),
    vector_store=MyChromaStore("http://chroma:8000"),
)
```

---

## 3. 与平台 SPI 的映射（15 端口→canonical→interface_versions）

> 对应 design/DESIGN.md §6，与平台 §10.4 严格对齐。

### 3.1 映射表

| SDK 领域端口（domain） | 平台 SPI 端口（§10.4 canonical） | interface_versions | SDK 角色 | 默认 Adapter（bom.yaml） |
| --- | --- | --- | --- | --- |
| `Gateway` | **Gateway** | 1.2.0 | 生产（invoke） | Higress（core） |
| `AgentRuntime` | **AgentRuntime** | 1.3.0 | 生产（Load/Run） | LangGraph 绑定执行（core） |
| `LLMProvider` | **LLMProvider** | 1.0.0 | 生产（chat/embed/rerank/stream） | Qwen-Cloud / OpenAI / Claude（core 第三方） |
| `VectorStore` | **VectorStore** | 1.1.0 | 生产（upsert/search/delete） | Qdrant（core）/ Milvus（optional） |
| `Cache` | **Cache** | 1.0.0 | 生产（语义/精确缓存） | Redis（core）/ Valkey（optional, OSI） |
| `Auth` | **Auth** | 1.0.0 | 消费（租户 Token 校验） | Keycloak（core） |
| `Tracing` | **Tracing** | 1.0.0 | 生产（span） | Langfuse（core）/ OTel（core 基线） |
| `RAG` | **RAG** | 1.0.0 | 消费（检索回填） | RAGFlow（core） |
| `LowCode` | **LowCode** | 1.0.0 | 消费（画布→AgentSpec） | 自研 React Flow（core）/ Dify（reference） |
| `Workflow` | **Workflow** | 1.0.0 | 消费（长任务编排） | Temporal（optional） |
| `Sandbox` | **Sandbox** | 1.0.0 | 消费（代码执行隔离） | Kata / E2B（optional） |
| `CICD` | **CICD** | 1.0.0 | 消费（灰度发布） | ArgoCD / Istio（optional） |
| `MultiTenancy` | **MultiTenancy** | 1.0.0 | 消费（租户隔离上下文） | Capsule（optional） |
| `MLOps` | **MLOps** | 1.0.0 | 消费（微调/蒸馏） | MLflow（optional） |
| `Eval` | **Eval** | 1.0.0 | 消费（评测回流） | Promptfoo / DeepEval / Ragas（core/optional） |

### 3.2 角色分类

| SDK 角色 | 含义 | 涉及端口 |
|----------|------|----------|
| **生产（producer）** | SDK 主动调用平台服务，生成数据或执行操作 | Gateway、AgentRuntime、LLMProvider、VectorStore、Cache、Tracing |
| **消费（consumer）** | SDK 消费平台下发的上下文/配置，不主动修改 | Auth、RAG、LowCode、Workflow、Sandbox、CICD、MultiTenancy、MLOps、Eval |

### 3.3 关键约束

1. **端口名逐字一致**: SDK 端口名与 `bom.yaml` `spi` 字段完全相同（§16.2）；新增/替换实现永不需改核心（§10.6 Registry 模型）
2. **同级故障转移**: 同一 `LLMProvider` SPI 背后并存自托管与多个第三方实现，跨实现故障转移由平台 `ModelRouter` 负责（§4.4.4/§4.4.5）
3. **VectorStore 无感切换**: 切换 VectorStore 提供方时由平台迁移 Job 双写校验（§10.4），SDK 经 SPI 工厂拿对应 Adapter，业务代码零改动
4. **配置覆盖优先级**: 构造参数 > 环境变量 > `pyproject.toml` `[tool.openstrata]` > 平台 Manifest 下发（§12）

### 3.4 端口间关系（数据流）

```
Gateway ──→ LLMProvider ──→ (chat/embed/rerank/stream)
Gateway ──→ VectorStore ──→ RAG ──→ (检索回填 prompt)
Gateway ──→ Cache ──→ Session ──→ (会话记忆)
AgentRuntime ──→ Tracing ──→ (span 上报)
Gateway ──→ Auth ──→ MultiTenancy ──→ (租户上下文)
Workflow ──→ Sandbox ──→ (长任务代码隔离)
MLOps ──→ Eval ──→ LowCode ──→ (微调→评测→画布导出)
```

### 3.5 Python 特定约束

- 所有 Port 协议使用 `typing.Protocol`（结构化子类型，无需显式继承）
- `stream()` 返回 `AsyncIterator[StreamChunk]`（Python async/await 原语）
- `Cache.get()` 返回 `Optional[bytes]` 明确表示缓存未命中
- 注入通过 `Client(...)` 构造参数
- 兼容 `async` 和同步两种调用上下文；默认实现支持 `from_env()` 函数式简化

---

> **关联文档**: skills/SKILLS.md（扩展点与编码规则）· specs/SPECS.md（SPI 版本契约与配置键）· design/DESIGN.md（完整设计）
