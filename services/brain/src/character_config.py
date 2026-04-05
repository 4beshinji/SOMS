"""
Character personality loader.

Search order (first found wins):
  1. config/characters/user/{CHARACTER_ID}.yaml   — user-created, git-ignored
  2. config/characters/presets/{CHARACTER_ID}.yaml — shipped presets

CHARACTER_ID env var selects the active character (default: "default").
"""

import os
from pathlib import Path
from typing import Any

import yaml

_CHARACTER_ID = os.getenv("CHARACTER_ID", "default")

# Config dir: /app/config in Docker, or inferred relative to this file for local dev
_CONFIG_DIR = Path(os.getenv("CONFIG_DIR", Path(__file__).parent.parent / "config"))
_CHARS_DIR = _CONFIG_DIR / "characters"


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load character YAML %s: %s", path, e)
        return None


def _load_character(character_id: str) -> dict[str, Any]:
    """Load character by ID. User dir takes priority over presets."""
    for subdir in ("user", "presets"):
        data = _load_yaml(_CHARS_DIR / subdir / f"{character_id}.yaml")
        if data:
            return data

    # Fallback: if requested ID not found, try default preset
    if character_id != "default":
        import logging
        logging.getLogger(__name__).warning(
            "Character '%s' not found, falling back to default", character_id
        )
        data = _load_yaml(_CHARS_DIR / "presets" / "default.yaml")
        if data:
            return data

    # Hard-coded last resort (keeps service running even without config mount)
    return {
        "identity": {
            "name": "SOMS",
            "name_reading": "ソムス",
            "first_person": "わたし",
            "second_person": "あなた",
        },
        "personality": {
            "archetype": "コミカルなオフィス管理AI",
            "traits": ["普段はコミカルで親しみやすい", "効率と最適化を愛している"],
            "formality": 1,
            "expressiveness": 3,
        },
        "speaking_style": {
            "endings": {
                "neutral": ["だよ", "だね"],
                "caring": ["てね"],
                "humorous": ["なんちゃって"],
                "alert": ["！"],
            },
            "vocabulary": {"prefer": [], "avoid": []},
            "catchphrase": "最適化こそ正義。",
        },
    }


CHARACTER: dict[str, Any] = _load_character(_CHARACTER_ID)


def build_character_prompt_section(character: dict = CHARACTER) -> str:
    """Build the character personality section for LLM system prompt."""
    identity = character["identity"]
    personality = character["personality"]
    style = character["speaking_style"]

    formality_map = {0: "ため口", 1: "カジュアル", 2: "標準", 3: "丁寧語", 4: "最敬語"}
    formality_label = formality_map.get(personality["formality"], "カジュアル")

    lines = [
        "## キャラクター設定",
        f"- 名前: {identity['name']}（{identity['name_reading']}）",
        f"- 一人称: {identity['first_person']}、二人称: {identity['second_person']}",
        f"- 性格: {personality['archetype']}",
        f"- 特徴: {', '.join(personality['traits'])}",
        f"- 敬語レベル: {formality_label}",
    ]

    for tone, endings in style["endings"].items():
        lines.append(f"- {tone}の語尾例: {', '.join(endings)}")

    avoid = style.get("vocabulary", {}).get("avoid", [])
    if avoid:
        lines.append(f"- 禁止語彙: {', '.join(avoid)}")

    if style.get("catchphrase"):
        lines.append(f"- 決め台詞: {style['catchphrase']}")

    return "\n".join(lines)
