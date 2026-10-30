import json
import random
import re
from collections import defaultdict, deque
from pathlib import Path
from time import monotonic


class StickerSelector:
    def __init__(self, catalog_path, rate=0.35, cooldown=30):
        data = json.loads(Path(catalog_path).read_text(encoding="utf-8-sig"))
        self.assets = data["assets"]
        self.rate = rate
        self.cooldown = cooldown
        self.last_sent = {}
        self.recent = defaultdict(lambda: deque(maxlen=20))
        self.random = random.Random()


    def candidates(self, context, session="default", limit=8):
        text = str(context).lower()
        recent = self.recent[session]

        semantic_groups = {
            "难过与疲惫": (
                "好累", "累死", "累了", "疲惫", "困死",
                "困了", "想睡", "熬夜", "没精神",
                "难受", "伤心", "难过", "委屈",
            ),
            "开心与得意": (
                "哈哈", "笑死", "开心", "高兴",
                "好耶", "太棒", "赢了", "成功了", "嘿嘿", "笑得",
            ),
            "亲近与安慰": (
                "可爱", "喜欢你", "抱抱", "摸摸",
                "安慰", "辛苦", "想你", "想我", "害羞", "贴贴", "rua", "揉揉", "蹭蹭",
            ),
            "AI与token": (
                "token", "模型", "烧钱", "api",
                "deepseek", "人工智能", "大模型",
            ),
            "生气与抗议": (
                "生气", "气死", "讨厌", "不服",
                "抗议", "过分", "可恶",
            ),
            "疑惑与思考": (
                "为什么", "怎么回事", "不懂",
                "疑惑", "迷惑", "思考", "什么意思",
            ),
            "玩梗与整活": (
                "绷不住", "整活", "玩梗",
                "离谱", "抽象", "逆天",
            ),
            "吃饭与摸鱼": (
                "吃饭", "饿了", "干饭", "零食",
                "摸鱼", "偷懒", "休息",
            ),
            "招呼与回应": (
                "你好", "早上好", "晚安",
                "早安", "在吗", "拜拜",
            ),
            "吐槽与傲娇": (
                "吐槽", "傲娇", "哼", "嘴硬",
            ),
        }

        scored = []
        recent_scored = []
        for asset in self.assets:
            name = asset["name"]

            category = str(asset.get("category", "")).lower()
            description = str(asset.get("description", "")).lower()
            tags = [
                str(tag).lower()
                for tag in asset.get("tags", [])
            ]

            score = 0

            if description and description in text:
                score += 8

            for tag in tags:
                if tag and tag in text:
                    score += 5

            if category and category in text:
                score += 4

            for group, keywords in semantic_groups.items():
                if category == group.lower():
                    hits = sum(
                        1 for word in keywords
                        if word in text
                    )
                    if hits:
                        score += 4 + min(hits, 3)

            # 允许部分描述关键词匹配，避免完全依赖整句
            for keyword in (
                "偷吃", "token", "开心", "生气",
                "难过", "害羞", "睡觉", "吃饭",
                "抱抱", "摸鱼", "疑惑", "委屈",
            ):
                if keyword in text and (
                    keyword in description
                    or any(keyword in tag for tag in tags)
                ):
                    score += 3

            if score > 0:
                if name in recent:
                    recent_scored.append((score, asset))
                else:
                    scored.append((score, asset))

        # A small category must not remain exhausted forever. Prefer fresh
        # matches; only if all matches are recent, allow the least recent ones.
        # Never immediately repeat the last queued asset, even for a one-item pool.
        if not scored and recent_scored:
            last_positions = {name: i for i, name in enumerate(recent)}
            recent_scored = [item for item in recent_scored if item[1]["name"] != recent[-1]]
            recent_scored.sort(key=lambda item: (last_positions[item[1]["name"]], -item[0]))
            return [asset for _, asset in recent_scored[:max(0, limit)]]

        self.random.shuffle(scored)
        scored.sort(key=lambda item: item[0], reverse=True)

        return [asset for _, asset in scored[:max(0, limit)]]

    def context_candidates(self, current, history, session="default", limit=8):
        # Old chat must never crowd current intent out of the candidate pool.
        current_matches = self.candidates(current, session, limit=limit)
        names = {a['name'] for a in current_matches}
        old_matches = self.candidates(history, session, limit=limit)
        return (current_matches + [a for a in old_matches if a['name'] not in names])[:limit]

    def choose(self, context, session="default", now=None):
        now = monotonic() if now is None else now

        if now - self.last_sent.get(session, -1e12) < self.cooldown:
            return None

        options = self.candidates(context, session)
        if not options:
            return None

        if self.random.random() >= self.rate:
            return None

        chosen = options[0]
        self.recent[session].append(chosen["name"])
        self.last_sent[session] = now
        return chosen

    def fallback_candidates(self, context, session, allowed):
        """Narrow, current-turn casual cues; never infer mood from old history."""
        text = str(context).lower()
        categories = set()
        cues = {
            "亲近与安慰": r"rua|揉揉|蹭蹭|贴贴|抱抱|可爱|喜欢你|想你|想我|害羞",
            "开心与得意": r"哈哈|嘿嘿|笑死|笑得|开心|好耶|太棒|高兴",
            "招呼与回应": r"谢谢|谢啦|谢了|早安|晚安|你好",
            "吐槽与傲娇": r"嘴硬|傲娇|哼哼",
            "玩梗与整活": r"整活|玩梗|绷不住|离谱",
            "AI与token": r"(?:充|偷吃|喂).{0,8}token|token.{0,8}(?:充|偷吃|喂)",
            "吃饭与摸鱼": r"吃饭|干饭|白饭|摸鱼|零食",
        }
        for category, pattern in cues.items():
            if category == "开心与得意" and re.search(r"不开心|不高兴|开心不起来|笑不出来|不是.{0,3}开心", text):
                continue
            if category == "亲近与安慰" and re.search(r"不想你|不想我|别想我|不要抱|别抱", text):
                continue
            if re.search(pattern, text):
                categories.add(category)
        return [a for a in self.candidates(text, session, limit=len(self.assets))
                if a['name'] in allowed and a.get('category') in categories]
