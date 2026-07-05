from __future__ import annotations

import re
from typing import Any

from app.logging import get_logger

log = get_logger(__name__)

_CACHE: dict[str, Any] = {}
_client: Any | None = None


def _langfuse_client() -> Any | None:
    import os
    global _client
    if _client is not None:
        return _client
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        return None
    try:
        from langfuse import Langfuse
        _client = Langfuse()
        return _client
    except Exception as e:
        log.warning("prompts.langfuse_unavailable", error=str(e))
        return None


def clear_cache() -> None:
    _CACHE.clear()
    log.debug("prompts.cache_cleared")


def _fetch(client: Any, name: str) -> Any | None:
    try:
        return client.get_prompt(name, label="latest")
    except Exception as e:
        log.warning("prompts.fetch_failed", name=name, error=str(e))
        return None


def _compile(prompt_obj: Any, vars: dict[str, Any]) -> str:
    try:
        return prompt_obj.compile(**vars)
    except Exception:
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vars.get(m.group(1), "")), prompt_obj.prompt)


def get_system_prompt(persona_id: str) -> str:
    name = f"persona-{persona_id}-system"
    if name in _CACHE:
        return _CACHE[name]
    client = _langfuse_client()
    if client is not None:
        p = _fetch(client, name)
        if p is not None:
            text = getattr(p, "prompt", "")
            if text:
                _CACHE[name] = text
                log.info("prompts.registry.fetched", name=name, source="langfuse")
                return text
    try:
        from app.debate.engine import persona_system_prompt
        text = persona_system_prompt(persona_id, target_kind="company")
        _CACHE[name] = text
        log.info("prompts.registry.fetched", name=name, source="disk")
        return text
    except Exception as e:
        log.warning("prompts.disk_fallback_failed", name=name, error=str(e))
        return ""


_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _compile_inline(template: str, vars: dict[str, Any]) -> str:
    return _VAR_RE.sub(lambda m: str(vars.get(m.group(1), "")), template)


_DEFAULT_TASK_TEMPLATES: dict[str, str] = {
    "thesis": (
        "# Data context for {{target}}\n\n"
        "{{context_md}}\n\n"
        "# Your task\n"
        "Produce an initial investment thesis for {{target}} as of {{target_date}}.\n"
        "This is your independent first take.\n\n"
        "{{hint}}\n\n"
        "Submit a single structured thesis.\n"
        "CRITICAL FORMAT: key_drivers and data_used must be FLAT lists of plain strings. "
        "Do NOT nest lists. Do NOT use XML tags.\n"
    ),
    "rebuttal": (
        "# Data context for {{target}}\n\n"
        "{{context_md}}\n\n"
        "# Other personas' theses (round {{round}})\n\n"
        "{{prior_theses_block}}\n\n"
        "# Your task\n"
        "Read the other personas' theses and produce a rebuttal.\n\n"
        "{{hint}}\n\n"
        "CRITICAL FORMAT: targets, concessions, and disagreements must be FLAT lists of "
        "plain strings. Do NOT nest lists. Do NOT use XML tags.\n"
    ),
    "verdict": (
        "{{tally_block}}"
        "# Debate summary\n"
        "Target: {{target}}\nDomain: {{domain}}\nDate: {{target_date}}\n\n"
        "# Data context\n{{context_md}}\n\n"
        "# Round 0 theses\n{{theses_block}}\n\n"
        "# Rebuttals\n{{rebuttals_block}}\n\n"
        "Produce a single structured verdict.\n"
        "CRITICAL FORMAT: points_of_agreement and points_of_disagreement must be FLAT "
        "lists of plain strings. Do NOT nest lists. Do NOT use XML tags.\n"
    ),
}


def get_task_template(task_name: str, **vars: str) -> str:
    name = f"task-{task_name}"
    cache_key = name
    if cache_key in _CACHE:
        return _compile_inline(_CACHE[cache_key], vars)
    client = _langfuse_client()
    if client is not None:
        p = _fetch(client, name)
        if p is not None:
            text = getattr(p, "prompt", "")
            if text:
                _CACHE[cache_key] = text
                log.info("prompts.registry.fetched", name=name, source="langfuse")
                return _compile_inline(text, vars)
    fallback = _DEFAULT_TASK_TEMPLATES.get(task_name, "")
    if fallback:
        log.info("prompts.registry.fetched", name=name, source="disk")
        return _compile_inline(fallback, vars)
    return ""
