"""One Claude helper for every AI step: give it a Pydantic model, get back a
validated instance of it.

    llm = LLM()
    fit = llm.structured(system=..., prompt=..., output=BrandFit, effort="low")

* Uses structured outputs (output_config.format), so the reply is JSON that
  matches the schema. Pydantic then enforces the finer rules (lengths,
  ranges) that the API schema leaves out; a reply that fails them is sent back
  to Claude with the errors, up to `max_attempts` times.
* Network errors, 429s and 5xx are retried by the SDK itself (max_retries).
* Server-side refusal fallback is on by default (LLM_FALLBACKS=default); set
  LLM_FALLBACKS=off to disable. A refusal that survives it raises LLMRefusal.
* Untrusted text (captions, reviews) must be wrapped with `untrusted()`.
"""

from __future__ import annotations

import copy
import html
import json
import logging
from typing import Callable, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from .config import REPO_ROOT, env

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = REPO_ROOT / "prompts"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# JSON-schema keywords the API's structured outputs may not accept. Pydantic
# still enforces them locally after the reply comes back.
_LOCAL_ONLY_KEYWORDS = {
    "title", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "format", "examples",
}


class LLMError(Exception):
    pass


class LLMRefusal(LLMError):
    pass


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def untrusted(tag: str, text: str | None) -> str:
    """Wrap scraped or user text so the prompt can tell Claude to treat it as data."""
    return f"<{tag}>{html.escape(text or '', quote=False)}</{tag}>"


def api_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema -> self-contained schema for structured outputs:
    $refs inlined, every object closed (additionalProperties false) with all
    properties required, local-only keywords removed."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            out = {k: walk(v) for k, v in node.items() if k not in _LOCAL_ONLY_KEYWORDS}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class LLM:
    def __init__(self, client=None, model: str | None = None, max_attempts: int = 3):
        self.client = client or anthropic.Anthropic(max_retries=4)
        self.model = model or env("ANTHROPIC_MODEL", "claude-opus-5-5")
        self.max_attempts = max_attempts
        self.fallbacks = (env("LLM_FALLBACKS", "default") or "default").lower() != "off"

    def _call(self, system: str, messages: list, schema: dict, effort: str, max_tokens: int):
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if self.fallbacks:
            return self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        return self.client.messages.create(**kwargs)

    def structured(
        self,
        *,
        system: str,
        prompt: str,
        output: type[T],
        effort: str = "medium",
        max_tokens: int = 16000,
        check: Callable[[T], list[str]] | None = None,
    ) -> T:
        """`check` returns a list of problems for rules that need context
        (e.g. "ids must be from this list"); problems are sent back to Claude
        like validation errors."""
        schema = api_schema(output)
        messages: list = [{"role": "user", "content": prompt}]
        last_error = None

        for attempt in range(1, self.max_attempts + 1):
            response = self._call(system, messages, schema, effort, max_tokens)
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise LLMRefusal(f"Claude declined ({getattr(details, 'category', None)})")
            text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
            if response.stop_reason == "max_tokens":
                last_error = "reply was cut off at max_tokens"
                max_tokens = min(max_tokens * 2, 64000)
                continue
            try:
                parsed = output.model_validate_json(text)
                problems = check(parsed) if check else []
                if not problems:
                    return parsed
            except ValidationError as e:
                problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
            last_error = "; ".join(problems)
            log.info("structured output rejected (attempt %s): %s", attempt, last_error)
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That JSON broke these rules: {last_error}. Send the corrected JSON only."},
            ]
        raise LLMError(f"No valid output after {self.max_attempts} attempts: {last_error}")


def ai_mode() -> str:
    """'llm' when Claude is configured, else 'template' (deterministic text so
    the backend still runs end to end without a key). Override with AI_MODE."""
    mode = (env("AI_MODE") or "").lower()
    if mode in ("llm", "template"):
        return mode
    return "llm" if env("ANTHROPIC_API_KEY") else "template"


def to_json(data) -> str:
    """Stable JSON for prompts (sorted keys keep the prompt cache-friendly)."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
