"""Client facade (① access layer): the OpenAI-compatible call entry.

Holds the tenant token and exposes the 5 first-class objects' operations plus
all 15 SPI ports (as attributes). Wired by constructor injection; defaults are
stdlib-only so ``Client.from_env()`` is usable offline (DESIGN §3).
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Optional

from openstrata_sdk.config import Config, load_config
from openstrata_sdk.domain.models import (
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    GatewayRequest,
    GatewayResponse,
    RerankRequest,
    RerankResponse,
    StreamChunk,
)
from openstrata_sdk.domain.objects import Retriever, Session
from openstrata_sdk.infrastructure.adapters import (
    EchoLLMProvider,
    HTTPGateway,
    InMemoryCache,
    InMemoryVectorStore,
    LocalAgentRuntime,
    LocalAuth,
    LoggingCICD,
    LoggingEval,
    LoggingGateway,
    LoggingLowCode,
    LoggingMLOps,
    LoggingMultiTenancy,
    LoggingRAG,
    LoggingSandbox,
    LoggingWorkflow,
    NoOpTracing,
)


class Client:
    def __init__(
        self,
        *,
        gateway=None,
        llm_provider=None,
        vector_store=None,
        cache=None,
        auth=None,
        tracing=None,
        agent_runtime=None,
        rag=None,
        lowcode=None,
        workflow=None,
        sandbox=None,
        cicd=None,
        multitenancy=None,
        mlops=None,
        eval_=None,
        config: Optional[Config] = None,
        tenant_token: Optional[str] = None,
    ) -> None:
        self._config = config or Config()
        self.tenant_token = tenant_token
        self._gateway = gateway or LoggingGateway()
        self._llm = llm_provider or EchoLLMProvider()
        self._vs = vector_store or InMemoryVectorStore()
        self._cache = cache or InMemoryCache()
        self._auth = auth or LocalAuth()
        self._tracing = tracing or NoOpTracing()
        self._ar = agent_runtime or LocalAgentRuntime()
        self._rag = rag or LoggingRAG()
        self._lowcode = lowcode or LoggingLowCode()
        self._workflow = workflow or LoggingWorkflow()
        self._sandbox = sandbox or LoggingSandbox()
        self._cicd = cicd or LoggingCICD()
        self._mt = multitenancy or LoggingMultiTenancy()
        self._mlops = mlops or LoggingMLOps()
        self._eval = eval_ or LoggingEval()

    # -- assembly ---------------------------------------------------------- #
    @classmethod
    def new_default(cls) -> "Client":
        """Offline-safe default wiring (all stdlib adapters)."""
        return cls()

    @classmethod
    def from_env(cls, **overrides: Any) -> "Client":
        """Assemble from env / config fragment, falling back to offline defaults."""
        cfg = load_config(Config.from_env(), Config.from_file())
        gateway = None
        if cfg.gateway_base_url:
            gateway = HTTPGateway(cfg.gateway_base_url, token=overrides.get("tenant_token"))
        kwargs: Dict[str, Any] = {"config": cfg}
        if gateway is not None:
            kwargs["gateway"] = gateway
        for k in ("tenant_token",):
            if k in overrides:
                kwargs[k] = overrides[k]
        return cls(**kwargs)

    # -- SPI port accessors ------------------------------------------------ #
    @property
    def gateway(self): return self._gateway
    @property
    def llm_provider(self): return self._llm
    @property
    def vector_store(self): return self._vs
    @property
    def cache(self): return self._cache
    @property
    def auth(self): return self._auth
    @property
    def tracing(self): return self._tracing
    @property
    def agent_runtime(self): return self._ar
    @property
    def rag(self): return self._rag
    @property
    def lowcode(self): return self._lowcode
    @property
    def workflow(self): return self._workflow
    @property
    def sandbox(self): return self._sandbox
    @property
    def cicd(self): return self._cicd
    @property
    def multitenancy(self): return self._mt
    @property
    def mlops(self): return self._mlops
    @property
    def eval(self): return self._eval

    # -- conversational API ------------------------------------------------ #
    def chat(self, req: ChatRequest, session: Optional[Session] = None) -> ChatResponse:
        resp = self._llm.chat(req)
        if session is not None and resp.content:
            session.remember("last_assistant", resp.content)
        return resp

    def embed(self, req: EmbedRequest) -> EmbedResponse:
        return self._llm.embed(req)

    def rerank(self, req: RerankRequest) -> RerankResponse:
        return self._llm.rerank(req)

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]:
        async for chunk in self._llm.stream(req):
            yield chunk

    def invoke(self, req: GatewayRequest) -> GatewayResponse:
        return self._gateway.invoke(req)

    # -- first-class object factories ------------------------------------- #
    def session(self, user_id: str, ttl: float = 3600.0) -> Session:
        return Session(user_id, self._cache, ttl)

    def retriever(self, kb_id: str) -> Retriever:
        return Retriever(kb_id, self._vs, self._rag)
