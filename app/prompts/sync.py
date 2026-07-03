from __future__ import annotations

import argparse
import os
import sys

from app.logging import get_logger

log = get_logger(__name__)

_PERSONA_IDS = (
    "buffett", "lynch", "dalio", "burry", "greenspan", "bernanke",
    "volcker", "dimon", "eisman", "grantham", "simons", "taleb",
    "wood", "gundlach", "thaler",
)
_TASK_NAMES = ("thesis", "rebuttal", "verdict")


def _require_env() -> tuple[str, str]:
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        print("ERROR: Langfuse credentials missing. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (and optionally LANGFUSE_HOST) before running this command.", file=sys.stderr)
        sys.exit(2)
    return pk, sk


def _build_persona_text(persona_id: str) -> str:
    from app.debate.engine import persona_system_prompt
    return persona_system_prompt(persona_id, target_kind="company")


def _cmd_push(args: argparse.Namespace) -> int:
    _require_env()
    from app.prompts.registry import _DEFAULT_TASK_TEMPLATES, _langfuse_client
    client = _langfuse_client()
    if client is None:
        print("ERROR: Langfuse client not available.", file=sys.stderr)
        return 2
    personas = [args.persona] if args.persona else list(_PERSONA_IDS)
    n = 0
    for pid in personas:
        name = f"persona-{pid}-system"
        text = _build_persona_text(pid)
        try:
            client.create_prompt(name=name, prompt=text, labels=["persona", "system"], type="text")
            print(f"  pushed {name}")
            n += 1
        except Exception as e:
            print(f"  FAILED {name}: {e}", file=sys.stderr)
    for tname in _TASK_NAMES:
        name = f"task-{tname}"
        text = _DEFAULT_TASK_TEMPLATES.get(tname, "")
        try:
            client.create_prompt(name=name, prompt=text, labels=["task", tname], type="text")
            print(f"  pushed {name}")
            n += 1
        except Exception as e:
            print(f"  FAILED {name}: {e}", file=sys.stderr)
    from app.prompts.registry import clear_cache
    clear_cache()
    print(f"OK: pushed {len(personas)} persona(s) + {len(_TASK_NAMES)} task(s)")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    _require_env()
    from app.prompts.registry import _langfuse_client
    client = _langfuse_client()
    if client is None:
        return 2
    try:
        page = client.api.prompts.list(limit=50)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    for item in page.data:
        labels = getattr(item, "labels", []) or []
        print(f"  {item.name} v{item.version} labels={labels}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    _require_env()
    from app.prompts.registry import _DEFAULT_TASK_TEMPLATES, _langfuse_client
    client = _langfuse_client()
    if client is None:
        return 2
    drift = 0
    for pid in _PERSONA_IDS:
        name = f"persona-{pid}-system"
        try:
            p = client.get_prompt(name, label="latest")
            remote = p.prompt if hasattr(p, "prompt") else ""
        except Exception:
            print(f"  MISSING {name}")
            drift += 1
            continue
        local = _build_persona_text(pid)
        if local.strip() != remote.strip():
            print(f"  DRIFT {name} (local {len(local)} chars, remote {len(remote)} chars)")
            drift += 1
        else:
            print(f"  ok {name}")
    for tname in _TASK_NAMES:
        name = f"task-{tname}"
        try:
            p = client.get_prompt(name, label="latest")
            remote = p.prompt if hasattr(p, "prompt") else ""
        except Exception:
            print(f"  MISSING {name}")
            drift += 1
            continue
        local = _DEFAULT_TASK_TEMPLATES.get(tname, "")
        if local.strip() != remote.strip():
            print(f"  DRIFT {name}")
            drift += 1
        else:
            print(f"  ok {name}")
    print(f"\nDrift count: {drift}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.prompts.sync", description="Sync Langfuse prompts")
    sub = p.add_subparsers(dest="command", required=True)
    p_push = sub.add_parser("push", help="Push personas + tasks to Langfuse")
    p_push.add_argument("--persona", help="Push only this persona")
    p_push.set_defaults(func=_cmd_push)
    p_list = sub.add_parser("list", help="List prompts in Langfuse")
    p_list.set_defaults(func=_cmd_list)
    p_diff = sub.add_parser("diff", help="Compare disk vs Langfuse")
    p_diff.set_defaults(func=_cmd_diff)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
