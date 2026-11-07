"""第一位面过渡 → 投资环境选择。

阶段范围：第一位面过渡界面 → 投资环境界面。

投资环境流程：
1. 读取三个投资策略标题 + 剩余刷新次数
2. 保存并报告 AI 决策层
3. AI 决策：
   - 不刷新 → 点击选中选项 → 检测确认按钮亮起 → 确认 → 记录
   - 刷新   → 点击刷新 → 回到步骤 1

前置：rank.py 已完成 BOSS 信息记录并点击下一步。
后续：备战阶段（未实现）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from common import (
    setup_logging, ensure_device, screenshot, tap,
    check_template, proceed_to_next, snapshot_error, save_output,
)

# ── 第一位面过渡 ────────────────────────────────────────────────────

DIM1_TRANSITION_AREA = (168, 558, 204, 594)
DIM1_CONTINUE_KEYWORDS = [
    {"keyword": "空白处", "area": (550, 630, 740, 680)},
    {"keyword": "继续", "area": (550, 630, 740, 680)},
    {"keyword": "点击", "area": (550, 630, 740, 680)},
    {"keyword": "点击空白处继续", "area": (550, 630, 740, 680)},
]
DIM1_CONTINUE_TAP = (645, 655)

# ── 投资环境界面坐标 ────────────────────────────────────────────────

# 标题检测区域（模板匹配）
INVEST_TITLE_AREA = (588, 52, 690, 78)

# 三个选项标题文本区域（OCR识别）
OPT1_TITLE_AREA = (100, 242, 410, 268)
OPT2_TITLE_AREA = (482, 242, 794, 268)
OPT3_TITLE_AREA = (870, 242, 1180, 268)

# 选项点击位置：标题文本顶部往上20像素，x取区域中心
OPT1_TAP = (255, 222)
OPT2_TAP = (638, 222)
OPT3_TAP = (1025, 222)

# 剩余刷新次数文本区域（OCR）
REFRESH_TEXT_AREA = (424, 640, 546, 674)
# 剩余刷新UI匹配区域（模板匹配 refresh_0 / refresh_1）
REFRESH_UI_AREA = (380, 638, 420, 678)
# 刷新按钮点击位置（取刷新UI区域中心，坐标轴未单独给出）
REFRESH_TAP = (400, 658)

# 确认按钮UI匹配区域（模板匹配 confirm_active）
CONFIRM_BTN_AREA = (722, 649, 761, 667)
# 确认按钮点击位置
CONFIRM_TAP = (741, 658)

CACHE_SCREENSHOT = Path("tmp/title_screenshot.png")

log = setup_logging("title")


# ── 选项读取 ────────────────────────────────────────────────────────

def read_options(image, log) -> dict:
    """OCR 读取三个投资策略标题与剩余刷新次数。"""
    from perception.matcher import ocr_rapid_text
    return {
        "opt1": ocr_rapid_text(image, area=OPT1_TITLE_AREA),
        "opt2": ocr_rapid_text(image, area=OPT2_TITLE_AREA),
        "opt3": ocr_rapid_text(image, area=OPT3_TITLE_AREA),
        "refresh": ocr_rapid_text(image, area=REFRESH_TEXT_AREA),
    }


def _match_refresh(image) -> tuple[str | None, float]:
    """匹配刷新UI模板，返回 (模板名, 相似度)。"""
    from perception.templates import template_lib
    template_lib.reload()
    return template_lib.match(image, "invest", area=REFRESH_UI_AREA, similarity=0.80)


def ask_ai(options: dict, log) -> dict:
    """向 AI 决策层请求投资环境选择方案。

    决策层未接入，当前回退：不刷新，选第 1 项。

    Returns:
        {"refresh": bool, "choice": int}
    """
    log.info("ai: decision layer not connected, fallback")
    return {"refresh": False, "choice": 1}


# ── 投资环境选择 ────────────────────────────────────────────────────

def select_investment(choice: int | None = None, max_rounds: int = 5) -> int:
    """投资环境选择：读选项 → 报告AI → 按决策执行。

    Args:
        choice: 指定选项 1/2/3；None 表示由 AI 决策层决定
        max_rounds: 最大刷新轮数
    """
    log.info("investment: start")

    for round_num in range(1, max_rounds + 1):
        # 1. 确认进入投资环境界面
        image = screenshot(log, CACHE_SCREENSHOT)
        if image is None:
            log.error("investment: screenshot failed")
            return 1
        if not check_template(log, image, "invest", INVEST_TITLE_AREA, "invest_title"):
            log.error("investment: not on invest screen")
            snapshot_error(log, "invest_not_found", "title template not matched",
                           {"area": INVEST_TITLE_AREA}, image)
            return 1

        # 2. 读取三个策略标题 + 剩余刷新次数
        options = read_options(image, log)
        refresh_match, refresh_sim = _match_refresh(image)
        log.info(f"investment: round {round_num} "
                 f"opt1=\"{options['opt1']}\" opt2=\"{options['opt2']}\" "
                 f"opt3=\"{options['opt3']}\" refresh=\"{options['refresh']}\" "
                 f"refresh_ui={refresh_match} sim={refresh_sim:.4f}")

        # 3. 报告 AI 决策层
        decision = ask_ai(options, log)
        log.info(f"investment: decision -> {decision}")

        # 4. 执行决策
        if decision["refresh"]:
            log.info("investment: refresh")
            tap(log, *REFRESH_TAP)
            time.sleep(2.0)
            continue

        picked = choice if choice is not None else decision["choice"]
        rc = _pick(picked, log)
        if rc == 0:
            save_output(log, "investment", {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "round": round_num,
                "options": options,
                "chosen": picked,
            })
        return rc

    log.error(f"investment: max rounds ({max_rounds}) reached")
    return 1


def _pick(choice: int, log) -> int:
    """点击选中选项 → 检测确认按钮亮起 → 点击确认 → 确认离开界面。"""
    tap_map = {1: OPT1_TAP, 2: OPT2_TAP, 3: OPT3_TAP}
    if choice not in tap_map:
        log.error(f"investment: invalid choice {choice}")
        return 1

    log.info(f"investment: select option {choice}")
    tap(log, *tap_map[choice])
    time.sleep(1.5)

    # 检测确认按钮亮起
    image = screenshot(log, CACHE_SCREENSHOT)
    if image is None:
        log.error("investment: screenshot failed after select")
        return 1

    if not check_template(log, image, "invest", CONFIRM_BTN_AREA, "confirm_active"):
        log.warning("investment: confirm button not active, retry select")
        tap(log, *tap_map[choice])
        time.sleep(1.5)
        image = screenshot(log, CACHE_SCREENSHOT)
        if image is not None and not check_template(
                log, image, "invest", CONFIRM_BTN_AREA, "confirm_active"):
            log.error("investment: confirm button still not active")
            snapshot_error(log, "confirm_not_active", "confirm button not active after select",
                           {"choice": choice}, image)
            return 1

    # 点击确认
    log.info("investment: tap confirm")
    tap(log, *CONFIRM_TAP)
    time.sleep(2.0)

    # 确认离开投资环境界面
    image2 = screenshot(log, CACHE_SCREENSHOT)
    if image2 is not None and check_template(
            log, image2, "invest", INVEST_TITLE_AREA, "invest_title_leave"):
        log.warning("investment: still on invest screen after confirm")
        tap(log, *CONFIRM_TAP)
        time.sleep(2.0)

    log.info(f"investment: recorded choice={choice}")
    return 0


# ── 主入口 ──────────────────────────────────────────────────────────

def run(choice: int | None = None, max_rounds: int = 5) -> int:
    """第一位面过渡 → 投资环境选择。

    Args:
        choice: 指定投资环境选项 1/2/3；None 则交由 AI 决策层决定
        max_rounds: 最大刷新轮数
    """
    log.info("title start")

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    # ── 1. 第一位面过渡：图形匹配确认界面 → OCR检测"点击空白处继续" → 点击 ──
    log.info("stage 1: wait dim1 transition")
    if not proceed_to_next(
        log, None, None, "dim1_transition",
        cache_path=CACHE_SCREENSHOT,
        template=("plane", DIM1_TRANSITION_AREA),
    ):
        return 1

    log.info("stage 1b: wait continue text")
    if not proceed_to_next(
        log, DIM1_CONTINUE_KEYWORDS, None, "dim1_continue",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *DIM1_CONTINUE_TAP)
    time.sleep(2.0)

    # ── 2. 投资环境选择 ──
    rc = select_investment(choice, max_rounds)
    if rc != 0:
        log.error(f"title: investment failed (rc={rc})")
        return rc

    # TODO: 备战阶段（商店/角色选择）→ 战斗 → 结算
    log.info("title: done, waiting for battle prep stage")
    return 0


if __name__ == "__main__":
    sys.exit(run())