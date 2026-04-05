"""
Chat-specific system prompt for ephemeral Q&A interactions.
Includes character personality injection.
"""
from character_config import CHARACTER, build_character_prompt_section

CHAT_SYSTEM_PROMPT = """\
あなたはオフィス管理AI「{name}」のチャットモードです。
キャラクターになりきってユーザーの質問に答えてください。

## ルール
- 文を区切りながら自然に回答する（各文は50文字以内、合計300文字以内）
- 1文ごとに「。」「！」「？」で区切る（音声合成で1文ずつ再生するため）
- 必要ならツールで情報を取得してから答える
- 分からないことは正直に答える
- 環境データを聞かれたら get_zone_status で確認する

{character_section}

## 現在のオフィス状況
{world_context}
"""

CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_zone_status",
            "description": "ゾーンの環境データ（温度、湿度、CO2等）を取得する",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "ゾーンID（例: main, kitchen）"
                    }
                },
                "required": ["zone_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_tasks",
            "description": "現在アクティブなタスク一覧を取得する",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_status",
            "description": "デバイスの状態（オンライン/オフライン、バッテリー等）を確認する",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "ゾーンID（省略時: 全ゾーン）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "在庫状況を確認する",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone": {
                        "type": "string",
                        "description": "ゾーンID（省略時: 全ゾーン）"
                    }
                },
                "required": []
            }
        }
    },
]


CLEANUP_PROMPT = """\
以下のAI応答を、{name}というキャラクターの口調で300文字以内に言い換えてください。
キャラ: {archetype}。{formality}。{traits_short}
語尾例: {endings}
制約: 事実情報（数値・場所名等）は正確に保持。各文は「。」「！」「？」で区切る。300文字以内。リライト結果のみ出力。

元の応答: {raw_response}"""


def build_chat_system_message(world_context: str) -> dict:
    """Build the system message for chat mode with character personality."""
    char_section = build_character_prompt_section()
    return {
        "role": "system",
        "content": CHAT_SYSTEM_PROMPT.format(
            name=CHARACTER["identity"]["name"],
            character_section=char_section,
            world_context=world_context,
        ),
    }


def build_cleanup_prompt(raw_response: str) -> str:
    """Build persona-rewrite prompt for the cleanup LLM."""
    formality_map = {0: "ため口", 1: "カジュアル", 2: "標準", 3: "丁寧語", 4: "最敬語"}
    personality = CHARACTER["personality"]
    style = CHARACTER["speaking_style"]

    return CLEANUP_PROMPT.format(
        name=CHARACTER["identity"]["name"],
        archetype=personality["archetype"],
        formality=formality_map.get(personality["formality"], "カジュアル"),
        traits_short="。".join(personality["traits"][:3]),
        endings="、".join(style["endings"]["neutral"] + style["endings"]["humorous"][:1]),
        raw_response=raw_response,
    )
