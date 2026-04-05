"""Serendipity-focused motion retriever for avatar gesture selection.

Ported from hems project. Scoring pipeline:
  final = 1.0 * bm25 + 0.8 * tone_affinity + 0.5 * (1 - decay) + 0.3 * novelty
  → temperature softmax sampling (not argmax)

Motion IDs must match the frontend procedural-motions.ts registry.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class MotionEntry:
    id: str
    description: str
    tags: list[str]
    duration: float
    category: str
    tokens: set[str] = field(default_factory=set)


# All procedural motions available in the frontend.
# description + tags are Japanese for BM25 matching against Japanese chat text.
MOTION_DEFS: list[dict] = [
    {
        "id": "nod_agree",
        "description": "軽くうなずいて同意や確認を示す。了解、報告、同意に使用。",
        "tags": ["同意", "確認", "了解", "うなずき", "報告", "はい", "わかった", "なるほど"],
        "duration": 1.5,
        "category": "reaction",
    },
    {
        "id": "head_tilt",
        "description": "首をかしげて疑問や興味を示す。質問、不明点、好奇心に使用。",
        "tags": ["疑問", "質問", "不思議", "かな", "どう", "興味", "わからない"],
        "duration": 1.2,
        "category": "reaction",
    },
    {
        "id": "small_bow",
        "description": "軽くお辞儀する。お礼、丁寧な挨拶、よろしくに使用。",
        "tags": ["お辞儀", "挨拶", "ありがとう", "よろしく", "どうぞ", "丁寧", "すみません"],
        "duration": 2.0,
        "category": "greeting",
    },
    {
        "id": "look_around",
        "description": "周囲を見回す仕草。探し物、周囲確認、警戒に使用。",
        "tags": ["見回す", "周囲", "確認", "探す", "どこ", "場所"],
        "duration": 2.5,
        "category": "idle",
    },
    {
        "id": "thinking_pose",
        "description": "考え中の仕草。提案やアドバイス、思考中に使用。",
        "tags": ["思考", "提案", "アドバイス", "考え", "ヒント", "たぶん", "かもしれない"],
        "duration": 2.0,
        "category": "idle",
    },
    {
        "id": "surprise_back",
        "description": "驚いて少し後ろにのけぞる。予想外、びっくり、急な変化に使用。",
        "tags": ["驚き", "びっくり", "急", "予想外", "えっ", "まさか", "すごい"],
        "duration": 1.3,
        "category": "reaction",
    },
    {
        "id": "emphatic_nod",
        "description": "力強く深くうなずく。強い同意、納得、激励に使用。",
        "tags": ["強い同意", "納得", "そうだ", "絶対", "もちろん", "間違いない", "頑張"],
        "duration": 1.8,
        "category": "reaction",
    },
    {
        "id": "slow_shake",
        "description": "ゆっくり首を横に振る。否定、残念、困り顔に使用。",
        "tags": ["否定", "残念", "ダメ", "無理", "困", "しかたない", "ごめん"],
        "duration": 2.0,
        "category": "reaction",
    },
    {
        "id": "perk_up",
        "description": "パッと顔を上げて注目する。注意喚起、重要情報、アラートに使用。",
        "tags": ["注目", "注意", "警告", "危険", "重要", "アラート", "やばい", "大変"],
        "duration": 1.4,
        "category": "alert",
    },
]

# Tone → category affinity bias
AFFINITY: dict[str, dict[str, float]] = {
    "alert": {"alert": 1.0, "reaction": 0.3},
    "caring": {"greeting": 0.6, "reaction": 0.5, "idle": 0.3},
    "humorous": {"reaction": 0.5, "idle": 0.4, "greeting": 0.2},
    "neutral": {"reaction": 0.3, "idle": 0.3, "greeting": 0.1},
}

# Tone → sampling temperature (higher = more exploratory)
TEMPERATURE: dict[str, float] = {
    "humorous": 1.5,
    "alert": 0.5,
    "neutral": 0.8,
    "caring": 1.0,
}

DECAY_HALF_LIFE = 15  # uses before penalty halves


def _tokenize(text: str) -> set[str]:
    """Japanese-friendly tokenizer: character bigrams + whitespace split."""
    cleaned = re.sub(r"[。、！？\s.,!?\-\n]+", " ", text).strip()
    tokens: set[str] = set()
    for word in cleaned.split():
        if len(word) >= 2:
            tokens.add(word)
        for i in range(len(word) - 1):
            tokens.add(word[i : i + 2])
    return tokens


class MotionRetriever:
    def __init__(self) -> None:
        self.motions: list[MotionEntry] = []
        self._usage: dict[str, dict] = {}
        self._global_seq = 0

        for m in MOTION_DEFS:
            entry = MotionEntry(
                id=m["id"],
                description=m["description"],
                tags=m["tags"],
                duration=m["duration"],
                category=m["category"],
            )
            text = f"{entry.description} {' '.join(entry.tags)}"
            entry.tokens = _tokenize(text)
            self.motions.append(entry)
            self._usage[entry.id] = {"count": 0, "last_seq": 0}

        logger.info(f"MotionRetriever loaded {len(self.motions)} motions")

    def select(self, text: str, tone: str = "neutral") -> Optional[str]:
        """Select a motion_id for the given speech text and tone."""
        if not self.motions:
            return None

        query_tokens = _tokenize(text)
        scores: list[tuple[str, float]] = []

        for m in self.motions:
            bm25 = self._score_bm25(query_tokens, m)
            affinity = self._tone_affinity(tone, m.category)
            decay = self._usage_decay(m.id)
            novelty = self._novelty_bonus(m.id)

            final = 1.0 * bm25 + 0.8 * affinity + 0.5 * (1 - decay) + 0.3 * novelty
            scores.append((m.id, final))

        temperature = TEMPERATURE.get(tone, 0.8)
        selected = self._softmax_sample(scores, temperature)

        if selected:
            self._record_usage(selected)

        return selected

    def _score_bm25(self, query_tokens: set[str], motion: MotionEntry) -> float:
        if not query_tokens or not motion.tokens:
            return 0.0
        overlap = len(query_tokens & motion.tokens)
        return overlap / (len(motion.tokens) + 5)

    def _tone_affinity(self, tone: str, category: str) -> float:
        return AFFINITY.get(tone, {}).get(category, 0.0)

    def _usage_decay(self, motion_id: str) -> float:
        usage = self._usage.get(motion_id)
        if not usage or usage["count"] == 0:
            return 0.0
        uses_since = self._global_seq - usage["last_seq"]
        return math.exp(-0.693 * uses_since / DECAY_HALF_LIFE)

    def _novelty_bonus(self, motion_id: str) -> float:
        usage = self._usage.get(motion_id)
        if not usage or usage["count"] == 0:
            return math.log(2)
        return math.log(1 + 1 / usage["count"])

    def _softmax_sample(
        self, scores: list[tuple[str, float]], temperature: float
    ) -> Optional[str]:
        if not scores:
            return None
        max_s = max(s for _, s in scores)
        exps = []
        for mid, s in scores:
            exps.append((mid, math.exp((s - max_s) / max(temperature, 0.01))))
        total = sum(e for _, e in exps)
        if total == 0:
            return random.choice([mid for mid, _ in scores])

        r = random.random() * total
        cumulative = 0.0
        for mid, e in exps:
            cumulative += e
            if r <= cumulative:
                return mid
        return exps[-1][0]

    def _record_usage(self, motion_id: str) -> None:
        self._global_seq += 1
        if motion_id in self._usage:
            self._usage[motion_id]["count"] += 1
            self._usage[motion_id]["last_seq"] = self._global_seq
