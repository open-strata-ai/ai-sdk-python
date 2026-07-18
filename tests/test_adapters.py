"""Adapter tests: default stdlib SPI implementations satisfy the ports."""

import asyncio

from openstrata_sdk.domain.models import (
    AgentSpec,
    ChatRequest,
    ChatMessage,
    DeploySpec,
    Doc,
    EmbedRequest,
    EvalSpec,
    FineTuneSpec,
    GatewayRequest,
    RerankRequest,
    WorkflowSpec,
)
from openstrata_sdk.infrastructure.adapters import (
    EchoLLMProvider,
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


def test_echo_llm_chat_embed_rerank():
    llm = EchoLLMProvider()
    resp = llm.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert resp.content == "echo: hi"

    emb = llm.embed(EmbedRequest(inputs=["a", "b"]))
    assert len(emb.vectors) == 2 and len(emb.vectors[0]) == 8

    rr = llm.rerank(RerankRequest(query="q", docs=["short", "a much longer doc"]))
    assert rr.results[0].doc == "a much longer doc"


def test_echo_llm_stream():
    async def run():
        chunks = [c async for c in EchoLLMProvider().stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")]))]
        return "".join(c.delta for c in chunks), chunks[-1].finish_reason

    text, reason = asyncio.run(run())
    assert text == "echo: hi"
    assert reason == "stop"


def test_vector_store_cosine_search():
    vs = InMemoryVectorStore()
    vs.upsert("kb", [
        Doc(id="a", text="alpha", vector=[1.0, 0.0, 0.0]),
        Doc(id="b", text="beta", vector=[0.0, 1.0, 0.0]),
    ])
    hits = vs.search("kb", [0.9, 0.1, 0.0], top_k=1)
    assert hits[0].id == "a"
    assert hits[0].score > 0.9
    vs.delete("kb", ["a"])
    assert vs.search("kb", [1.0, 0.0, 0.0], top_k=5)[0].id == "b"


def test_cache_ttl():
    c = InMemoryCache()
    c.set("k", b"v", ttl=0)
    assert c.get("k") is None
    c.set("k2", b"v2", ttl=3600)
    assert c.get("k2") == b"v2"


def test_local_agent_runtime():
    rt = LocalAgentRuntime()
    spec = AgentSpec.builder("a").build()
    h = rt.load(spec)
    assert h.id == "a"
    out = rt.run(h, {"x": 1})
    assert out["output"] == {"x": 1}


def test_local_auth_and_tracing():
    ctx = LocalAuth().validate_token("")
    assert ctx.tenant_id == "anonymous"
    ctx2 = LocalAuth().validate_token("t1")
    assert ctx2.tenant_id == "t1"
    span = NoOpTracing().start_span("s")
    assert span.name == "s"


def test_logging_adapters_callable():
    LoggingGateway().invoke(GatewayRequest(path="/x"))
    LoggingRAG().retrieve("q", "kb", 1)
    LoggingLowCode().export_spec("c")
    LoggingWorkflow().submit(WorkflowSpec(name="w"))
    LoggingSandbox().execute("print(1)", "python")
    LoggingCICD().deploy(DeploySpec(name="d"))
    LoggingMultiTenancy().resolve_tenant("t")
    LoggingMLOps().submit_fine_tune(FineTuneSpec(base_model="m", dataset="d"))
    LoggingEval().run_eval(EvalSpec(name="e", dataset="d"))
