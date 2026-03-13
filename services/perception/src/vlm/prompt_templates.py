"""
VLM prompt templates for scene analysis.
Each template is a Japanese prompt tailored to a specific analysis type.
"""

_TEMPLATES = {
    "scene": (
        "あなたはオフィスの監視カメラ映像を分析するAIです。\n"
        "この画像のゾーン「{zone}」の現在の状況を簡潔に3文以内で記述してください。\n"
        "人数、活動内容、異常の有無を含めてください。"
    ),
    "occupancy_change": (
        "あなたはオフィスの監視カメラ映像を分析するAIです。\n"
        "ゾーン「{zone}」で人数が{prev_count}人から{person_count}人に変化しました。\n"
        "画像から人の出入りの状況を2文以内で説明してください。"
    ),
    "fall_candidate": (
        "あなたはオフィスの安全監視AIです。\n"
        "ゾーン「{zone}」でYOLOが転倒の可能性を検知しました（信頼度: {confidence:.0%}）。\n"
        "この画像を確認し、以下の形式で回答してください:\n"
        "判定: [転倒/非転倒/不明]\n"
        "状況: [1文で状況を説明]"
    ),
    "unusual_activity": (
        "あなたはオフィスの監視カメラ映像を分析するAIです。\n"
        "ゾーン「{zone}」で通常と異なる活動が検知されました。\n"
        "画像から何が起きているか2文以内で説明してください。"
    ),
}


def get_prompt(analysis_type: str, **context) -> str:
    """Get a formatted prompt for the given analysis type."""
    template = _TEMPLATES.get(analysis_type)
    if template is None:
        return f"この画像の状況を簡潔に説明してください。ゾーン: {context.get('zone', '不明')}"
    return template.format(**context)
