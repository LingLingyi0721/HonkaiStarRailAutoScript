"""游戏数据库查询接口。

供 AI 决策层直接调用，查询词缀描述、历史对局、相似投资环境。

- 静态数据（词缀/投资环境/角色/策略/羁绊/装备/竞争对手）：
  启动时从 CSV 直读内存 dict，查询直接走 dict。
- 对局记录（games）：JSON 文件 data/games.json 持久化，全量读改写。

不依赖 SQLite。
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent

AFFIX_CSV_PATH = DATA_DIR / "词缀.CSV"
INVEST_CSV_PATH = DATA_DIR / "投资环境一览.CSV"
CHARACTER_CSV_PATH = DATA_DIR / "角色详情.CSV"
STRATEGY_CSV_PATH = DATA_DIR / "投资策略.CSV"
BOND_CSV_PATH = DATA_DIR / "羁绊.CSV"
EQUIPMENT_CSV_PATH = DATA_DIR / "装备.CSV"
COMPETITOR_CSV_PATH = DATA_DIR / "竞争对手.CSV"
GAMES_JSON_PATH = DATA_DIR / "games.json"

# ── 内存表（启动时从 CSV 加载）──────────────────────────────────────

_affixes: dict[str, dict] = {}        # name -> row
_investments: dict[str, dict] = {}    # name -> row
_characters: dict[str, dict] = {}     # name -> row
_strategies: dict[str, dict] = {}     # name -> row
_bonds: dict[str, dict] = {}          # name -> row
_equipments: dict[str, dict] = {}     # name -> row
_competitors: dict[str, dict] = {}    # name -> row


def _load_csv(path: Path) -> list[dict]:
    """读取 CSV 为 dict 列表，文件不存在返回空列表。"""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def init_db() -> dict:
    """启动时从 CSV 加载静态数据到内存，并读取当前对局状态。

    返回各表条目数和当前 active 对局 id。
    """
    for r in _load_csv(AFFIX_CSV_PATH):
        name = r["名称"]
        _affixes[name] = {
            "id": len(_affixes),
            "name": name,
            "description": r["描述"],
            "category": "侵蚀" if name.startswith("侵蚀") else "常规",
        }

    for r in _load_csv(INVEST_CSV_PATH):
        _investments[r["名称"]] = {
            "id": len(_investments),
            "name": r["名称"],
            "effect": r["效果"],
            "characters": r.get("角色", ""),
            "equipment": r.get("装备", ""),
        }

    for r in _load_csv(CHARACTER_CSV_PATH):
        _characters[r["名称"]] = {
            "name": r["名称"],
            "cost": r["费用"].strip() or None,
            "position": r["站位"],
            "role": r["定位"],
            "bonds": r["羁绊"],
            "skills": r["技能"],
            "recommended_equips": r["推荐装备"],
            "hp_growth": r["生命增幅"],
            "front_power": r["基础前台强度"],
            "back_power": r["基础后台强度"],
            "speed_growth": r["速度增幅"],
            "heal_power": r["基础治疗强度"],
            "shield_power": r["基础护盾强度"],
        }

    for r in _load_csv(STRATEGY_CSV_PATH):
        _strategies[r["名字"]] = {
            "name": r["名字"],
            "rarity": r["稀有度"],
            "effect": r["内容"],
            "dimension": r["出现位面"],
        }

    for r in _load_csv(BOND_CSV_PATH):
        _bonds[r["羁绊名称"]] = {
            "name": r["羁绊名称"],
            "type": r["类型"],
            "trigger_counts": r["触发人数"],
            "base_effect": r["基础效果"],
            "graded_effect": r["分级效果"],
            "members": r["羁绊成员"],
        }

    for r in _load_csv(EQUIPMENT_CSV_PATH):
        _equipments[r["名称"]] = {
            "name": r["名称"],
            "type": r["类型"],
            "tag": r["标签"],
            "base_attr": r["基础属性"],
            "description": r["描述"],
            "source": r["获取途径"],
            "compatible_chars": r["适配角色"],
        }

    for r in _load_csv(COMPETITOR_CSV_PATH):
        _competitors[r["名称"]] = {
            "name": r["名称"],
            "boss": r["首领"],
            "elite_enemies": r["精英敌人"],
            "normal_enemies": r["普通敌人"],
        }

    active = get_active_game()
    active_id = active["id"] if active else None

    return {"affixes": len(_affixes), "investments": len(_investments),
            "characters": len(_characters), "strategies": len(_strategies),
            "bonds": len(_bonds), "equipments": len(_equipments),
            "competitors": len(_competitors), "active_game": active_id}


# ── 词缀查询 ──────────────────────────────────────────────────────

def get_affix(name: str) -> dict | None:
    """查单个词缀的描述。"""
    return _affixes.get(name)


def get_affix_description(name: str) -> str | None:
    """只查描述文本。"""
    row = _affixes.get(name)
    return row["description"] if row else None


def list_affixes(category: str | None = None) -> list[dict]:
    """列出所有词缀，可按类别筛选（常规/侵蚀）。"""
    if category:
        return [v for v in _affixes.values() if v["category"] == category]
    return list(_affixes.values())


def get_affixes_by_names(names: list[str]) -> list[dict]:
    """批量查词缀描述。"""
    return [_affixes[n] for n in names if n in _affixes]


# ── 投资环境查询 ──────────────────────────────────────────────────

def get_investment(name: str) -> dict | None:
    """查单个投资环境的完整信息。"""
    return _investments.get(name)


def get_investment_effect(name: str) -> str | None:
    """只查投资环境效果文本。"""
    row = _investments.get(name)
    return row["effect"] if row else None


def list_investments() -> list[dict]:
    """列出所有投资环境。"""
    return sorted(_investments.values(), key=lambda x: x["name"])


def get_investments_by_names(names: list[str]) -> list[dict]:
    """批量查投资环境。"""
    return [_investments[n] for n in names if n in _investments]


def search_investments(keyword: str) -> list[dict]:
    """按关键词搜索投资环境（名称或效果中包含关键词）。"""
    return [v for v in _investments.values()
            if keyword in v["name"] or keyword in v["effect"]]


# ── 角色查询 ──────────────────────────────────────────────────────

def get_character(name: str) -> dict | None:
    """查单个角色的完整信息。"""
    return _characters.get(name)


def list_characters(role: str | None = None, position: str | None = None) -> list[dict]:
    """列出所有角色，可按定位/站位筛选。"""
    result = []
    for v in _characters.values():
        if role and role not in v["role"]:
            continue
        if position and v["position"] != position:
            continue
        result.append(v)
    result.sort(key=lambda x: (x["cost"] or "", x["name"]))
    return result


def search_characters(keyword: str) -> list[dict]:
    """按关键词搜索角色（名称/技能/定位中包含关键词）。"""
    return [v for v in _characters.values()
            if keyword in v["name"] or keyword in v["skills"]
            or keyword in v["role"] or keyword in v["bonds"]]


def get_characters_by_cost(cost: int | str) -> list[dict]:
    """按费用查角色，支持多费用角色（如 '3/4/5'）。"""
    cost_str = str(cost)
    result = []
    for v in _characters.values():
        c = v["cost"]
        if c is None:
            continue
        if c == cost_str or f"/{cost_str}/" in f"/{c}/":
            result.append(v)
    result.sort(key=lambda x: x["name"])
    return result


# ── 投资策略查询 ──────────────────────────────────────────────────

def get_strategy(name: str) -> dict | None:
    return _strategies.get(name)


def list_strategies(rarity: str | None = None, dimension: str | None = None) -> list[dict]:
    result = []
    for v in _strategies.values():
        if rarity and v["rarity"] != rarity:
            continue
        if dimension and dimension not in v["dimension"]:
            continue
        result.append(v)
    result.sort(key=lambda x: (x["rarity"], x["name"]))
    return result


def search_strategies(keyword: str) -> list[dict]:
    return [v for v in _strategies.values()
            if keyword in v["name"] or keyword in v["effect"]]


# ── 羁绊查询 ──────────────────────────────────────────────────────

def get_bond(name: str) -> dict | None:
    return _bonds.get(name)


def list_bonds(bond_type: str | None = None) -> list[dict]:
    if bond_type:
        return [v for v in _bonds.values() if v["type"] == bond_type]
    return sorted(_bonds.values(), key=lambda x: (x["type"], x["name"]))


def search_bonds(keyword: str) -> list[dict]:
    return [v for v in _bonds.values()
            if keyword in v["name"] or keyword in v["base_effect"]
            or keyword in v["members"]]


# ── 装备查询 ──────────────────────────────────────────────────────

def get_equipment(name: str) -> dict | None:
    return _equipments.get(name)


def list_equipments(equip_type: str | None = None) -> list[dict]:
    if equip_type:
        return [v for v in _equipments.values() if v["type"] == equip_type]
    return sorted(_equipments.values(), key=lambda x: (x["type"], x["name"]))


def search_equipments(keyword: str) -> list[dict]:
    return [v for v in _equipments.values()
            if keyword in v["name"] or keyword in v["description"]
            or keyword in v["compatible_chars"]]


# ── 竞争对手查询 ──────────────────────────────────────────────────

def get_competitor(name: str) -> dict | None:
    return _competitors.get(name)


def list_competitors() -> list[dict]:
    return sorted(_competitors.values(), key=lambda x: x["name"])


# ── 对局记录（JSON 文件 data/games.json）───────────────────────────

def _load_games() -> list[dict]:
    """读取 games.json，文件不存在或内容损坏时返回空列表。"""
    if not GAMES_JSON_PATH.exists():
        return []
    try:
        with open(GAMES_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_games(games: list[dict]) -> None:
    """全量写回 games.json。"""
    with open(GAMES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(games, f, ensure_ascii=False, indent=2)


def _find_active(games: list[dict]) -> dict | None:
    """取 id 最大的 active 对局。"""
    candidates = [g for g in games if g.get("status") == "active"]
    return max(candidates, key=lambda g: g.get("id", 0)) if candidates else None


def start_new_game() -> None:
    """新对局开始：把所有 active 记录标记为 abandoned。"""
    games = _load_games()
    changed = False
    for g in games:
        if g.get("status") == "active":
            g["status"] = "abandoned"
            changed = True
    if changed:
        _save_games(games)


def save_game(
    rank: str | None = None,
    level: str | None = None,
    dimension1: str = "",
    dimension2: str = "",
    dimension3: str = "",
    difficulty: str | None = None,
    affixes: list[str] | None = None,
    result: str | None = None,
    status: str = "active",
) -> int:
    """写入一条对局记录，返回 id。"""
    games = _load_games()
    game_id = max((g.get("id", 0) for g in games), default=0) + 1
    games.append({
        "id": game_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rank": rank,
        "level": level,
        "dimension1": dimension1,
        "dimension2": dimension2,
        "dimension3": dimension3,
        "difficulty": difficulty,
        "affixes": list(affixes or []),
        "result": result,
        "status": status,
    })
    _save_games(games)
    return game_id


def update_active_game(
    rank: str | None = None,
    level: str | None = None,
    dimension1: str = "",
    dimension2: str = "",
    dimension3: str = "",
    difficulty: str | None = None,
    affixes: list[str] | None = None,
    result: str | None = None,
) -> int | None:
    """更新当前 active 对局的数据。没有 active 对局则新建一条。"""
    games = _load_games()
    active = _find_active(games)
    if active is None:
        return save_game(rank=rank, level=level, dimension1=dimension1,
                         dimension2=dimension2, dimension3=dimension3,
                         difficulty=difficulty, affixes=affixes, result=result)

    for key, val in [("rank", rank), ("level", level), ("dimension1", dimension1),
                     ("dimension2", dimension2), ("dimension3", dimension3),
                     ("difficulty", difficulty), ("result", result)]:
        if val is not None:
            active[key] = val
    if affixes is not None:
        active["affixes"] = list(affixes)

    _save_games(games)
    return active["id"]


def complete_active_game(result: str = "completed") -> None:
    """对局结束：把 active 记录标记为 completed。"""
    games = _load_games()
    changed = False
    for g in games:
        if g.get("status") == "active":
            g["status"] = result
            g["result"] = result
            changed = True
    if changed:
        _save_games(games)


def get_active_game() -> dict | None:
    """查当前 active 对局。"""
    return _find_active(_load_games())


def get_game(game_id: int) -> dict | None:
    """查单条对局记录。"""
    for g in _load_games():
        if g.get("id") == game_id:
            return g
    return None


def list_games(limit: int = 20) -> list[dict]:
    """查最近 N 条对局记录。"""
    games = sorted(_load_games(), key=lambda g: g.get("id", 0), reverse=True)
    return games[:limit]


def find_similar_games(
    affixes: list[str] | None = None,
    rank: str | None = None,
    min_overlap: int = 1,
    limit: int = 10,
) -> list[dict]:
    """查找词缀组合相似的历史对局。

    min_overlap: 至少重叠几个词缀才算相似。
    """
    games = sorted(_load_games(), key=lambda g: g.get("id", 0), reverse=True)

    result = []
    for g in games:
        game_affixes = g.get("affixes", [])
        overlap = len(set(affixes or []) & set(game_affixes))
        if overlap < min_overlap:
            continue
        if rank and g.get("rank") != rank:
            continue
        d = dict(g)
        d["affixes"] = game_affixes
        d["overlap"] = overlap
        result.append(d)

    result.sort(key=lambda x: x["overlap"], reverse=True)
    return result[:limit]


# ── 统计 ──────────────────────────────────────────────────────────

def affix_stats() -> list[dict]:
    """统计每个词缀在历史对局中出现的次数。"""
    counts: dict[str, int] = {}
    for g in _load_games():
        for name in g.get("affixes", []):
            counts[name] = counts.get(name, 0) + 1

    result = []
    for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        result.append({"name": name, "count": count,
                       "description": get_affix_description(name)})
    return result


def game_count() -> int:
    """总对局数。"""
    return len(_load_games())