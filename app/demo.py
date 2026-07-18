"""Offline demo for the OpenStrata Python SDK (not a publishing subject).

Run with the project venv::

    .venv/bin/python -m app.demo
"""

from __future__ import annotations

import asyncio

from openstrata_sdk import (
    AgentSpec,
    Client,
    ModelBinding,
    ObjectSchema,
    Guardrails,
    Tool,
)
from openstrata_sdk.domain.models import ChatRequest, ChatMessage


@Tool.register("order_lookup", input_schema=ObjectSchema("order_id", "string"))
def order_lookup(order_id: str) -> dict:
    return {"order_id": order_id, "status": "shipped"}


def main() -> None:
    client = Client.from_env()

    # 1) Chat
    resp = client.chat(ChatRequest(
        messages=[ChatMessage(role="user", content="Where is my order?")],
    ))
    print("chat ->", resp.content)

    # 2) Streaming
    async def stream_demo() -> None:
        chunks = []
        async for c in client.stream(ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
        )):
            chunks.append(c.delta)
        print("stream ->", "".join(chunks))

    asyncio.run(stream_demo())

    # 3) Declarative AgentSpec -> AgentRuntime load/run
    spec = (
        AgentSpec.builder("customer-service-v2")
        .tenant("tenant-b")
        .model_binding(ModelBinding(preferred="cloud-qwen-max",
                                    fallback_chain=["local-qwen2.5-72b"]))
        .input_schema(ObjectSchema("query", "string"))
        .output_schema(ObjectSchema("answer", "string"))
        .guardrails(Guardrails(checks=["injection_scan", "pii_scan"]))
        .with_tool_bindings("order_lookup")
        .build()
    )
    handle = client.agent_runtime.load(spec)
    out = client.agent_runtime.run(handle, {"query": "Where is my order?"})
    print("agent ->", out)

    # 4) Registered tool
    print("tool  ->", Tool.get("order_lookup").call(order_id="A-123"))

    # 5) Session / memory
    sess = client.session("user-123")
    sess.set_working_memory_ttl(3600)
    sess.remember("name", "Zhang")
    print("session recall ->", sess.recall("name"))


if __name__ == "__main__":
    main()
