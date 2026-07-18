"""Client facade tests (offline wiring via from_env / new_default)."""

import asyncio

from openstrata_sdk import AgentSpec, Client, ModelBinding, ObjectSchema
from openstrata_sdk.domain.models import ChatMessage, ChatRequest, GatewayRequest
from openstrata_sdk.domain.objects import Session


def test_client_from_env_chat_and_invoke():
    c = Client.from_env()
    resp = c.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert resp.content == "echo: hi"
    gw = c.invoke(GatewayRequest(path="/v1/chat"))
    assert gw.status == 200


def test_client_stream():
    async def run():
        chunks = [ch async for ch in Client.new_default().stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")]))]
        return "".join(ch.delta for ch in chunks)

    assert asyncio.run(run()) == "echo: hi"


def test_client_agent_runtime():
    c = Client.new_default()
    spec = (
        AgentSpec.builder("svc")
        .model_binding(ModelBinding(preferred="m"))
        .input_schema(ObjectSchema("query", "string"))
        .output_schema(ObjectSchema("answer", "string"))
        .build()
    )
    h = c.agent_runtime.load(spec)
    out = c.agent_runtime.run(h, {"query": "q"})
    assert out["agent"] == "svc"


def test_client_session_and_retriever():
    c = Client.from_env()
    sess: Session = c.session("u", ttl=3600)
    sess.remember("k", "v")
    assert sess.recall("k") == "v"
    retr = c.retriever("kb")
    assert retr.kb_id == "kb"
