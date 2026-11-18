from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from feng_workers.llm import LLM


class FakeClient:
    """Stands in for anthropic.Anthropic. `responder(kwargs, call_number)`
    returns a dict (sent back as the JSON reply), a SimpleNamespace (a raw
    response), or raises."""

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.responder(kwargs, len(self.calls))
        if isinstance(out, SimpleNamespace):
            return out
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               content=[SimpleNamespace(type="text", text=json.dumps(out, ensure_ascii=False))])


def fake_llm(responder) -> tuple[LLM, FakeClient]:
    client = FakeClient(responder)
    return LLM(client=client, model="test-model"), client


def make_creators(conn, n: int, city: str = "Sunnyvale", posts: int = 4, platform: str = "instagram") -> list[str]:
    ids = []
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    for i in range(n):
        handle = f"t_{uuid.uuid4().hex[:10]}"
        cid = conn.execute(
            "insert into creators (handle, display_name, platform, city, followers, source) "
            "values (%s, %s, %s, %s, %s, 'TEST') returning id",
            (handle, f"Test {i}", platform, city, 5000 + 1000 * i)).fetchone()[0]
        for j in range(posts):
            conn.execute(
                "insert into creator_posts (creator_id, url, caption, posted_at, likes, comments, source) "
                "values (%s, %s, %s, %s, %s, %s, 'TEST')",
                (cid, f"https://creators.example/{handle}/{j}",
                 f"Hotpot night {j} in {city} with friends, spicy broth" if j % 2 == 0 else f"Ramen crawl {j}",
                 now - timedelta(days=3 * j), 200 + 10 * j, 15 + j))
        ids.append(str(cid))
    return ids
