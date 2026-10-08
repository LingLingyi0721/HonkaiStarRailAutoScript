"""游戏数据库查询接口。

供 AI 决策层直接调用，查询词缀描述、历史对局、相似投资环境。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "game.db"
AFFIX_CSV_PATH = Path(__file__).resolve().parent / "词缀描述数据库.CSV"
INVEST_CSV_PATH = Path(__file__).resolve().parent / "投资环境一览.CSV"
CHARACTER_CSV_PATH = Path(__file__).resolve().parent / "角色详情.CSV"


def init_db() -> dict:
    """启动时初始化数据库。

    - 建表（如不存在）
    - 从 CSV 更新词缀表和投资环境表（静态数据，安全更新）
    - 检查 active 对局，有则保留不动
    - 返回 {"affixes": N, "investments": N, "active_game": id|None}
    """
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS affixes (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            category TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            effect TEXT,
            characters TEXT,
            equipment TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            rank TEXT,
            level TEXT,
            dimension1 TEXT,
            dimension2 TEXT,
            dimension3 TEXT,
            difficulty TEXT,
            affixes TEXT,
            result TEXT,
            status TEXT DEFAULT 'active'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS characters (
            name TEXT PRIMARY KEY,
            cost INTEGER,
            position TEXT,
            role TEXT,
            bonds TEXT,
            skills TEXT,
            recommended_equips TEXT,
            hp_growth TEXT,
            front_power TEXT,
            back_power TEXT,
            speed_growth TEXT,
            heal_power TEXT,
            shield_power TEXT
        )""")
        c.commit()

    affix_count = _update_affixes_from_csv()
    invest_count = _update_investments_from_csv()
    char_count = _update_characters_from_csv()

    active = get_active_game()
    active_id = active["id"] if active else None

    return {"affixes": affix_count, "investments": invest_count,
            "characters": char_count, "active_game": active_id}


def _update_affixes_from_csv() -> int:
    """从 CSV 更新词缀表（INSERT OR REPLACE，不 DROP）。"""
    import csv
    if not AFFIX_CSV_PATH.exists():
        return 0
    with _conn() as c:
        with open(AFFIX_CSV_PATH, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                name = r["名称"]
                category = "侵蚀" if name.startswith("侵蚀") else "常规"
                c.execute(
                    "INSERT OR REPLACE INTO affixes (name, description, category) VALUES (?, ?, ?)",
                    (name, r["描述"], category),
                )
        c.commit()
        return c.execute("SELECT COUNT(*) FROM affixes").fetchone()[0]


def _update_investments_from_csv() -> int:
    """从 CSV 更新投资环境表（INSERT OR REPLACE，不 DROP）。"""
    import csv
    if not INVEST_CSV_PATH.exists():
        return 0
    with _conn() as c:
        with open(INVEST_CSV_PATH, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                c.execute(
                    "INSERT OR REPLACE INTO investments (name, effect, characters, equipment) VALUES (?, ?, ?, ?)",
                    (r["名称"], r["效果"], r.get("角色", ""), r.get("装备", "")),
                )
        c.commit()
        return c.execute("SELECT COUNT(*) FROM investments").fetchone()[0]


def _update_characters_from_csv() -> int:
    """从 CSV 更新角色表（INSERT OR REPLACE，不 DROP）。"""
    import csv
    if not CHARACTER_CSV_PATH.exists():
        return 0
    with _conn() as c:
        with open(CHARACTER_CSV_PATH, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                c.execute(
                    """INSERT OR REPLACE INTO characters
                    (name, cost, position, role, bonds, skills, recommended_equips,
                     hp_growth, front_power, back_power, speed_growth, heal_power, shield_power)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["名称"],
                        int(r["费用"]) if r["费用"].strip() else None,
                        r["站位"],
                        r["定位"],
                        r["羁绊"],
                        r["技能"],
                        r["推荐装备"],
                        r["生命增幅"],
                        r["基础前台强度"],
                        r["基础后台强度"],
                        r["速度增幅"],
                        r["基础治疗强度"],
                        r["基础护盾强度"],
                    ),
                )
        c.commit()
        return c.execute("SELECT COUNT(*) FROM characters").fetchone()[0]


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── 词缀查询 ──────────────────────────────────────────────────────

def get_affix(name: str) -> dict | None:
    """查单个词缀的描述。"""
    with _conn() as c:
        row = c.execute("SELECT * FROM affixes WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def get_affix_description(name: str) -> str | None:
    """只查描述文本。"""
    with _conn() as c:
        row = c.execute("SELECT description FROM affixes WHERE name = ?", (name,)).fetchone()
    return row["description"] if row else None


def list_affixes(category: str | None = None) -> list[dict]:
    """列出所有词缀，可按类别筛选（常规/侵蚀）。"""
    with _conn() as c:
        if category:
            rows = c.execute("SELECT * FROM affixes WHERE category = ?", (category,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM affixes").fetchall()
    return [dict(r) for r in rows]


def get_affixes_by_names(names: list[str]) -> list[dict]:
    """批量查词缀描述。"""
    if not names:
        return []
    placeholders = ",".join("?" * len(names))
    with _conn() as c:
        rows = c.execute(
            f"SELECT * FROM affixes WHERE name IN ({placeholders})", names
        ).fetchall()
    return [dict(r) for r in rows]


# ── 投资环境查询 ──────────────────────────────────────────────────

def get_investment(name: str) -> dict | None:
    """查单个投资环境的完整信息。"""
    with _conn() as c:
        row = c.execute("SELECT * FROM investments WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def get_investment_effect(name: str) -> str | None:
    """只查投资环境效果文本。"""
    with _conn() as c:
        row = c.execute("SELECT effect FROM investments WHERE name = ?", (name,)).fetchone()
    return row["effect"] if row else None


def list_investments() -> list[dict]:
    """列出所有投资环境。"""
    with _conn() as c:
        rows = c.execute("SELECT * FROM investments ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_investments_by_names(names: list[str]) -> list[dict]:
    """批量查投资环境。"""
    if not names:
        return []
    placeholders = ",".join("?" * len(names))
    with _conn() as c:
        rows = c.execute(
            f"SELECT * FROM investments WHERE name IN ({placeholders})", names
        ).fetchall()
    return [dict(r) for r in rows]


def search_investments(keyword: str) -> list[dict]:
    """按关键词搜索投资环境（名称或效果中包含关键词）。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM investments WHERE name LIKE ? OR effect LIKE ?",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 角色查询 ──────────────────────────────────────────────────────

def get_character(name: str) -> dict | None:
    """查单个角色的完整信息。"""
    with _conn() as c:
        row = c.execute("SELECT * FROM characters WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def list_characters(role: str | None = None, position: str | None = None) -> list[dict]:
    """列出所有角色，可按定位/站位筛选。"""
    with _conn() as c:
        query = "SELECT * FROM characters"
        conditions = []
        params = []
        if role:
            conditions.append("role LIKE ?")
            params.append(f"%{role}%")
        if position:
            conditions.append("position = ?")
            params.append(position)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY cost, name"
        rows = c.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def search_characters(keyword: str) -> list[dict]:
    """按关键词搜索角色（名称/技能/定位中包含关键词）。"""
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM characters WHERE
            name LIKE ? OR skills LIKE ? OR role LIKE ? OR bonds LIKE ?""",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_characters_by_cost(cost: int) -> list[dict]:
    """按费用查角色。"""
    with _conn() as c:
        rows = c.execute("SELECT * FROM characters WHERE cost = ? ORDER BY name", (cost,)).fetchall()
    return [dict(r) for r in rows]


# ── 对局记录 ──────────────────────────────────────────────────────

def _ensure_games_table():
    """确保 games 表有 status 列（兼容旧库）。"""
    with _conn() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(games)").fetchall()]
        if "status" not in cols:
            c.execute("ALTER TABLE games ADD COLUMN status TEXT DEFAULT 'active'")
            c.commit()


def start_new_game() -> None:
    """新对局开始：把所有 active 记录标记为 abandoned。"""
    _ensure_games_table()
    with _conn() as c:
        c.execute("UPDATE games SET status = 'abandoned' WHERE status = 'active'")
        c.commit()


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
    _ensure_games_table()
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO games
            (timestamp, rank, level, dimension1, dimension2, dimension3, difficulty, affixes, result, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                rank, level, dimension1, dimension2, dimension3,
                difficulty,
                json.dumps(affixes or [], ensure_ascii=False),
                result,
                status,
            ),
        )
        c.commit()
    return cur.lastrowid


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
    _ensure_games_table()
    with _conn() as c:
        row = c.execute("SELECT id FROM games WHERE status = 'active' ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            game_id = row["id"]
            sets = []
            params = []
            for col, val in [("rank", rank), ("level", level), ("dimension1", dimension1),
                             ("dimension2", dimension2), ("dimension3", dimension3),
                             ("difficulty", difficulty), ("result", result)]:
                if val is not None:
                    sets.append(f"{col} = ?")
                    params.append(val)
            if affixes is not None:
                sets.append("affixes = ?")
                params.append(json.dumps(affixes, ensure_ascii=False))
            if sets:
                params.append(game_id)
                c.execute(f"UPDATE games SET {', '.join(sets)} WHERE id = ?", params)
                c.commit()
            return game_id
        else:
            return save_game(rank=rank, level=level, dimension1=dimension1,
                             dimension2=dimension2, dimension3=dimension3,
                             difficulty=difficulty, affixes=affixes, result=result)


def complete_active_game(result: str = "completed") -> None:
    """对局结束：把 active 记录标记为 completed。"""
    _ensure_games_table()
    with _conn() as c:
        c.execute("UPDATE games SET status = ?, result = ? WHERE status = 'active'",
                  (result, result))
        c.commit()


def get_active_game() -> dict | None:
    """查当前 active 对局。"""
    _ensure_games_table()
    with _conn() as c:
        row = c.execute("SELECT * FROM games WHERE status = 'active' ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        d = dict(row)
        d["affixes"] = json.loads(d["affixes"])
        return d
    return None


def get_game(game_id: int) -> dict | None:
    """查单条对局记录。"""
    with _conn() as c:
        row = c.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if row:
        d = dict(row)
        d["affixes"] = json.loads(d["affixes"])
        return d
    return None


def list_games(limit: int = 20) -> list[dict]:
    """查最近 N 条对局记录。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM games ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["affixes"] = json.loads(d["affixes"])
        result.append(d)
    return result


def find_similar_games(
    affixes: list[str] | None = None,
    rank: str | None = None,
    min_overlap: int = 1,
    limit: int = 10,
) -> list[dict]:
    """查找词缀组合相似的历史对局。

    min_overlap: 至少重叠几个词缀才算相似。
    """
    with _conn() as c:
        rows = c.execute("SELECT * FROM games ORDER BY id DESC").fetchall()

    result = []
    for r in rows:
        d = dict(r)
        game_affixes = json.loads(d["affixes"])
        overlap = len(set(affixes or []) & set(game_affixes))
        if overlap >= min_overlap:
            if rank and d["rank"] != rank:
                continue
            d["affixes"] = game_affixes
            d["overlap"] = overlap
            result.append(d)

    result.sort(key=lambda x: x["overlap"], reverse=True)
    return result[:limit]


# ── 统计 ──────────────────────────────────────────────────────────

def affix_stats() -> list[dict]:
    """统计每个词缀在历史对局中出现的次数。"""
    with _conn() as c:
        rows = c.execute("SELECT affixes FROM games").fetchall()

    counts: dict[str, int] = {}
    for r in rows:
        for name in json.loads(r["affixes"]):
            counts[name] = counts.get(name, 0) + 1

    # 关联词缀描述
    result = []
    for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        desc = get_affix_description(name)
        result.append({"name": name, "count": count, "description": desc})
    return result


def game_count() -> int:
    """总对局数。"""
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM games").fetchone()[0]