"""资产注册表：模板图片、区域定义、页面标识符。

=====================================================================
这层做什么
=====================================================================
集中管理所有"画面上要找的东西"的定义：
- 模板图片（Template）：从截图裁出来的小图，用于模板匹配
- 区域定义（AreaDef）：画面上的固定区域（金币显示区、商店格子区等）
- 页面标识（PageMark）：用于判断"当前在哪个页面"的特征组合

所有定义都用声明式写法（类似 Alas 的 assets.py），方便维护。
模板图片放在 assets/templates/ 下，区域坐标写在这里。

=====================================================================
和 Alas 的区别
=====================================================================
Alas: 每个按钮 = Button(area, color, button) 三元组，绑死在对象里
我们: 区域和模板分开定义，匹配函数在 matcher.py，定义在这里
      上层（pages.py / state.py）按需组合使用

原因：我们的决策层是 LLM，需要灵活组合感知结果，不适合绑死。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _ROOT / "assets" / "templates"


@dataclass
class TemplateDef:
    """模板图片定义。

    Attributes:
        name: 唯一标识名（如 "shop_refresh_btn"）
        file: 模板图片路径（相对 assets/templates/）
        area: 预期出现区域 (x1,y1,x2,y2)，None 则全图搜索
        similarity: 匹配阈值，默认 0.85
        binary: 是否用二值化匹配（对光照变化鲁棒）
    """
    name: str
    file: str
    area: tuple[int, int, int, int] | None = None
    similarity: float = 0.85
    binary: bool = False

    @property
    def path(self) -> Path:
        return TEMPLATE_DIR / self.file


@dataclass
class AreaDef:
    """画面区域定义。

    Attributes:
        name: 唯一标识名（如 "gold_display"）
        area: (x1, y1, x2, y2) 坐标
        desc: 人类可读描述
    """
    name: str
    area: tuple[int, int, int, int]
    desc: str = ""


@dataclass
class PageMark:
    """页面标识：用于判断当前在哪个页面。

    一个页面由若干"特征"共同确定。特征可以是：
    - 某个模板出现在预期位置（模板匹配）
    - 某个区域颜色符合预期（颜色匹配）

    Attributes:
        name: 页面名（如 "main_menu", "cw_shop"）
        templates: 需要匹配的模板列表（全部命中才算这个页面）
        color_checks: 需要颜色校验的区域列表 [(area, expected_color, threshold)]
        priority: 当多个页面同时匹配时，优先级高的胜出
    """
    name: str
    templates: list[TemplateDef] = field(default_factory=list)
    color_checks: list[tuple[AreaDef, tuple[int, int, int], int]] = field(default_factory=list)
    priority: int = 0


# ── 注册表 ──────────────────────────────────────────────────────────

_templates: dict[str, TemplateDef] = {}
_areas: dict[str, AreaDef] = {}
_pages: dict[str, PageMark] = {}


def register_template(t: TemplateDef) -> TemplateDef:
    _templates[t.name] = t
    return t


def register_area(a: AreaDef) -> AreaDef:
    _areas[a.name] = a
    return a


def register_page(p: PageMark) -> PageMark:
    _pages[p.name] = p
    return p


def get_template(name: str) -> TemplateDef:
    if name not in _templates:
        raise KeyError(f"模板未注册: {name}")
    return _templates[name]


def get_area(name: str) -> AreaDef:
    if name not in _areas:
        raise KeyError(f"区域未注册: {name}")
    return _areas[name]


def get_page(name: str) -> PageMark:
    if name not in _pages:
        raise KeyError(f"页面未注册: {name}")
    return _pages[name]


def all_pages() -> list[PageMark]:
    """返回所有已注册页面，按优先级降序。"""
    return sorted(_pages.values(), key=lambda p: -p.priority)


def all_templates() -> list[TemplateDef]:
    return list(_templates.values())


def all_areas() -> list[AreaDef]:
    return list(_areas.values())


# ── 预定义区域（1280x720 横屏） ────────────────────────────────────
# 这些坐标需要等游戏画面出来后用截图校准！现在先留占位。
# 标记 TODO 的都是待校准的。

# 通用 UI 区域
TOP_BAR = register_area(AreaDef("top_bar", (0, 0, 1280, 60), "顶部状态栏"))
BOTTOM_BAR = register_area(AreaDef("bottom_bar", (0, 660, 1280, 720), "底部操作栏"))

# 货币战争相关区域（TODO: 等游戏画面校准）
CW_GOLD_AREA = register_area(AreaDef("cw_gold", (10, 10, 120, 40), "金币数显示区"))
CW_INTEREST_AREA = register_area(AreaDef("cw_interest", (10, 40, 120, 70), "利息显示区"))
CW_SHOP_GRID = register_area(AreaDef("cw_shop_grid", (200, 100, 1080, 500), "商店角色格子区"))
CW_REFRESH_BTN = register_area(AreaDef("cw_refresh_btn", (1100, 400, 1200, 450), "刷新商店按钮"))
CW_BUY_BTN = register_area(AreaDef("cw_buy_btn", (1100, 500, 1200, 550), "购买按钮"))
CW_LEVEL_UP_BTN = register_area(AreaDef("cw_level_up_btn", (1100, 300, 1200, 350), "升人口按钮"))


# ── 预定义页面（TODO: 等游戏画面后补充模板和颜色） ──────────────────

# 主菜单
PAGE_MAIN = register_page(PageMark(
    name="main_menu",
    priority=10,
    # TODO: 等截图后补充模板和颜色特征
))

# 货币战争入口页
PAGE_CW_ENTRY = register_page(PageMark(
    name="cw_entry",
    priority=10,
))

# 货币战争商店页（买角色/升人口/刷新）
PAGE_CW_SHOP = register_page(PageMark(
    name="cw_shop",
    priority=10,
))

# 货币战争战斗准备页（站位/装备）
PAGE_CW_BATTLE_PREP = register_page(PageMark(
    name="cw_battle_prep",
    priority=10,
))

# 货币战争战斗进行中
PAGE_CW_BATTLE = register_page(PageMark(
    name="cw_battle",
    priority=10,
))

# 货币战争结算页
PAGE_CW_RESULT = register_page(PageMark(
    name="cw_result",
    priority=10,
))

# 加载中 / 下载页
PAGE_LOADING = register_page(PageMark(
    name="loading",
    priority=20,  # 高优先级：加载画面特征明显，先判
))