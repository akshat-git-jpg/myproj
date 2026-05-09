"""LLM helpers for tool detection + YT description generation.

Reads prompt templates from prompts/ at repo root.
Built on top of common.gemini.
"""

import os

from . import gemini
from .env import MYPROJ_ROOT

DEFAULT_MODEL = "gemini-2.5-flash"
PROMPTS_DIR = os.path.join(MYPROJ_ROOT, "prompts")


def _load_prompt(filename: str) -> str:
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def detect_tools(
    video_title: str,
    video_notes: str,
    candidate_tools: dict[str, str],
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """Return the subset of candidate_tools (by slug) the creator promotes.

    candidate_tools: {slug: display_name}
    Always returns slugs that exist in candidate_tools (filters hallucinations).
    """
    candidates_block = "\n".join(
        f"- {slug} — {display}" for slug, display in candidate_tools.items()
    )
    prompt = _load_prompt("detect-tools.md").format(
        video_title=video_title,
        video_notes=video_notes,
        candidates_block=candidates_block,
    )
    schema = {
        "type": "object",
        "properties": {"tools": {"type": "array", "items": {"type": "string"}}},
    }
    parsed = gemini.generate_json(model=model, prompt=prompt, schema=schema)
    raw = parsed.get("tools", []) if isinstance(parsed, dict) else []
    return [t for t in raw if t in candidate_tools]


def generate_description(
    video_title: str,
    video_notes: str,
    link_specs: list[dict],
    model: str = DEFAULT_MODEL,
) -> str:
    """link_specs: list of {tool, short_url, coupon_code} dicts.
    Returns the polished YT description text."""
    lines = []
    for spec in link_specs:
        coupon = spec.get("coupon_code", "")
        coupon_part = f" (coupon: {coupon})" if coupon else ""
        lines.append(f"- {spec['tool']} → {spec['short_url']}{coupon_part}")
    links_block = "\n".join(lines)

    prompt = _load_prompt("generate-description.md").format(
        video_title=video_title,
        video_notes=video_notes,
        links_block=links_block,
    )
    return gemini.generate_text(model=model, prompt=prompt)
