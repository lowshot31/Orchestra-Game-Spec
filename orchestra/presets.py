from __future__ import annotations

DEFAULT_PRESET = "balanced"

PRESET_INSTRUCTIONS = {
    "fast_draft": (
        "Preset: fast_draft\n"
        "- Move quickly from idea to usable draft.\n"
        "- Prefer MVP scope, simple mechanics, and short sections.\n"
        "- Leave deeper tradeoffs as open questions."
    ),
    "balanced": (
        "Preset: balanced\n"
        "- Balance creative exploration with production realism.\n"
        "- Keep the core loop, scope, risks, and final spec equally visible.\n"
        "- Make decisions concrete enough for a small game team to act on."
    ),
    "deep_review": (
        "Preset: deep_review\n"
        "- Stress-test feasibility, clarity, and production risk.\n"
        "- Challenge weak mechanics and unclear player motivation.\n"
        "- Produce sharper scope cuts and stronger implementation notes."
    ),
}


def normalize_preset(value: str | None) -> str:
    preset = (value or DEFAULT_PRESET).strip().lower() or DEFAULT_PRESET
    if preset not in PRESET_INSTRUCTIONS:
        return DEFAULT_PRESET
    return preset


def preset_instructions(value: str | None) -> str:
    return PRESET_INSTRUCTIONS[normalize_preset(value)]
