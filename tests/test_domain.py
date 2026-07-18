"""Domain-layer unit tests (AgentSpec, Tool, Session, Retriever, errors)."""

import pytest

from openstrata_sdk import (
    AgentSpec,
    Guardrails,
    ModelBinding,
    ObjectSchema,
    OpenStrataError,
    Retriever,
    Session,
    Tool,
)
from openstrata_sdk.domain.models import ChatMessage, ChatRequest
from openstrata_sdk.infrastructure.adapters import InMemoryCache, InMemoryVectorStore, LoggingRAG


def test_agent_spec_builder():
    spec = (
        AgentSpec.builder("cs-v2")
        .tenant("tenant-b")
        .model_binding(ModelBinding(preferred="cloud-qwen-max"))
        .input_schema(ObjectSchema("query", "string"))
        .output_schema(ObjectSchema("answer", "string"))
        .guardrails(Guardrails(checks=["injection_scan", "pii_scan"]))
        .with_tool_bindings("order_lookup")
        .build()
    )
    assert spec.api_version == "openstrata.cc/v1"
    assert spec.metadata["name"] == "cs-v2"
    assert spec.tenant == "tenant-b"
    assert spec.model_binding.preferred == "cloud-qwen-max"
    assert spec.input_schema.name == "query"
    assert spec.output_schema.name == "answer"
    assert spec.guardrails.checks == ["injection_scan", "pii_scan"]
    assert spec.tool_bindings == ["order_lookup"]


def test_guardrails_both_spellings():
    assert Guardrails(basic=["a"]).checks == ["a"]
    assert Guardrails(checks=["b"]).checks == ["b"]


def test_tool_register_and_call():
    @Tool.register("echo_tool", input_schema=ObjectSchema("text", "string"))
    def echo_tool(text: str) -> dict:
        return {"text": text}

    tool = Tool.get("echo_tool")
    assert tool is not None
    assert tool.call(text="hi") == {"text": "hi"}


def test_session_ttl_expiry_and_survival():
    cache = InMemoryCache()

    # zero TTL -> immediate miss
    s0 = Session("u0", cache, ttl=0)
    s0.put("k", b"v")
    assert s0.get("k") is None

    # real TTL -> survives
    s1 = Session("u1", cache, ttl=3600)
    s1.put("k", b"v")
    assert s1.get("k") == b"v"
    assert s1.recall("name") is None
    s1.remember("name", "Zhang")
    assert s1.recall("name") == "Zhang"


def test_retriever_uses_rag():
    vs = InMemoryVectorStore()
    rag = LoggingRAG()
    retriever = Retriever("kb-1", vs, rag)
    assert retriever.retrieve("anything", top_k=3) == []


def test_openstrata_error_model():
    err = OpenStrataError(code="RATE", port="Gateway", message="slow", retryable=True)
    assert err.code == "RATE"
    assert err.retryable is True
    assert "RATE" in str(err)


def test_chat_request_model():
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.messages[0].role == "user"
