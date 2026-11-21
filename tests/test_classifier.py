import asyncio
import json
import random
import pytest
import httpx

from src.schemas import Category, Priority, Ticket, TriageResult
from src.classifier import (
    ClassifierConfig,
    AsyncClassifier,
    ModelFailure,
)


def test_classifier_success_response():
    async def _test():
        expected_result = {
            "category": "technical_bug",
            "priority": "high",
            "confidence": 0.95,
            "reasoning": "Database connection timeout is a technical bug.",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            assert request.headers.get("Authorization") == "Bearer test-key"
            body = json.loads(request.read())
            assert body["model"] == "gpt-4o-mini"
            response_body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(expected_result)
                        }
                    }
                ]
            }
            return httpx.Response(200, json=response_body)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = ClassifierConfig(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
            )
            classifier = AsyncClassifier(client=client, config=config)
            ticket = Ticket(
                id="TCK-1",
                subject="DB Error",
                body="Database connection timeout on production.",
            )
            res = await classifier.classify(ticket)
            assert isinstance(res, TriageResult)
            assert res.category == Category.TECHNICAL_BUG
            assert res.priority == Priority.HIGH
            assert res.confidence == 0.95

    asyncio.run(_test())


def test_classifier_retry_on_429_then_succeed():
    async def _test():
        call_count = 0
        success_data = {
            "category": "billing",
            "priority": "medium",
            "confidence": 0.88,
            "reasoning": "Invoice query",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, json={"error": "Rate limited"})
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(success_data)}}]}
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = ClassifierConfig(
                api_key="test-key",
                backoff_base_seconds=0.01,
            )
            classifier = AsyncClassifier(client=client, config=config)
            ticket = Ticket(id="TCK-2", subject="Invoice", body="Where is my latest billing invoice?")
            res = await classifier.classify(ticket)
            assert call_count == 2
            assert isinstance(res, TriageResult)
            assert res.category == Category.BILLING

    asyncio.run(_test())


def test_classifier_terminal_failure_after_retries():
    async def _test():
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"error": "Internal Server Error"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = ClassifierConfig(
                api_key="test-key",
                max_retries=2,
                backoff_base_seconds=0.01,
            )
            classifier = AsyncClassifier(client=client, config=config)
            ticket = Ticket(id="TCK-3", subject="Help", body="Something broke in the system")
            res = await classifier.classify(ticket)

            assert call_count == 3  # initial + 2 retries
            assert isinstance(res, ModelFailure)
            assert res.escalation_reason == "model_unavailable"

    asyncio.run(_test())


def test_classifier_invalid_schema_response():
    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            # Invalid enum and extra prose
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Here is the result: {category: not_real}"}}]}
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = ClassifierConfig(api_key="test-key")
            classifier = AsyncClassifier(client=client, config=config)
            ticket = Ticket(id="TCK-4", subject="Bad output", body="Testing malformed model output")
            res = await classifier.classify(ticket)

            assert isinstance(res, ModelFailure)
            assert res.escalation_reason == "invalid_schema"

    asyncio.run(_test())


def test_classifier_failure_simulation():
    async def _test():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = ClassifierConfig(api_key="test-key")
            classifier = AsyncClassifier(
                client=client,
                config=config,
                rng=random.Random(42),
                failure_rate=1.0,
            )
            ticket = Ticket(id="TCK-5", subject="Chaos", body="Testing chaos failure simulation")
            res = await classifier.classify(ticket)

            assert isinstance(res, ModelFailure)
            assert res.escalation_reason == "model_unavailable"

    asyncio.run(_test())
