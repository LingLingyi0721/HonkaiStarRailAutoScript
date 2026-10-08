"""对局内操作：投资环境选择 → 备战阶段 → 战斗 → 结算。

投资环境选择流程：
1. 模板匹配确认进入投资环境界面
2. OCR识别三个选项标题
3. 外部输入选择选项（默认2）
4. 点击选中 → 检测确认按钮亮起 → 点击确认
5. 模板匹配确认离开投资环境界面
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from common import (
    setup_logging, ensure_device, screenshot, tap,
    check_template, check_keywords, proceed_to_next,
    snapshot_error,
)

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

# 确认按钮UI匹配区域（模板匹配 confirm_active）
CONFIRM_BTN_AREA = (722, 649, 761, 667)
# 确认按钮点击位置
CONFIRM_TAP = (741, 658)

CACHE_SCREENSHOT = Path("tmp/gameplay_screenshot.png")

log = setup_logging("gameplay")


# ── 投资环境选择 ────────────────────────────────────────────────────

def select_investment(choice: int = 2) -> int:
    """投资环境选择。

    Args:
        choice: 选项编号 1/2/3，默认2（测试用，需注释掉）。
                # TODO: 测试结束后改为外部输入或决策层选择
    """
    log.info("investment: start")

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    # 1. 确认进入投资环境界面
    log.info("investment: check title")
    image = screenshot(log, CACHE_SCREENSHOT)
    if image is None:
        log.error("investment: screenshot failed")
        return 1

    if not check_template(log, image, "invest", INVEST_TITLE_AREA, "invest_title"):
        log.error("investment: not on invest screen")
        snapshot_error(log, "invest_not_found", "title template not matched",
                       {"area": INVEST_TITLE_AREA}, image)
        return 1

    # 2. OCR识别三个选项标题
    from perception.matcher import ocr_rapid_text
    opt1_text = ocr_rapid_text(image, area=OPT1_TITLE_AREA)
    opt2_text = ocr_rapid_text(image, area=OPT2_TITLE_AREA)
    opt3_text = ocr_rapid_text(image, area=OPT3_TITLE_AREA)
    log.info(f"investment: opt1=\"{opt1_text}\"")
    log.info(f"investment: opt2=\"{opt2_text}\"")
    log.info(f"investment: opt3=\"{opt3_text}\"")

    # 3. 检测剩余刷新次数
    refresh_text = ocr_rapid_text(image, area=REFRESH_TEXT_AREA)
    log.info(f"investment: refresh=\"{refresh_text}\"")
    # 模板匹配刷新UI
    refresh_match, refresh_sim = _match_refresh(image)
    log.info(f"investment: refresh_ui={refresh_match} sim={refresh_sim:.4f}")

    # 4. 选择选项
    tap_map = {1: OPT1_TAP, 2: OPT2_TAP, 3: OPT3_TAP}
    if choice not in tap_map:
        log.error(f"investment: invalid choice {choice}")
        return 1

    log.info(f"investment: select option {choice}")
    tap(log, *tap_map[choice])
    time.sleep(1.5)

    # 5. 检测确认按钮亮起
    log.info("investment: check confirm active")
    image2 = screenshot(log, CACHE_SCREENSHOT)
    if image2 is None:
        log.error("investment: screenshot failed after select")
        return 1

    if not check_template(log, image2, "invest", CONFIRM_BTN_AREA, "confirm_active"):
        log.warning("investment: confirm button not active, retry select")
        tap(log, *tap_map[choice])
        time.sleep(1.5)
        image2 = screenshot(log, CACHE_SCREENSHOT)
        if image2 is not None and not check_template(log, image2, "invest", CONFIRM_BTN_AREA, "confirm_active"):
            log.error("investment: confirm button still not active")
            snapshot_error(log, "confirm_not_active", "confirm button not active after select",
                           {"choice": choice}, image2)
            return 1

    # 6. 点击确认
    log.info("investment: tap confirm")
    tap(log, *CONFIRM_TAP)
    time.sleep(2.0)

    # 7. 确认离开投资环境界面
    log.info("investment: check leave invest screen")
    image3 = screenshot(log, CACHE_SCREENSHOT)
    if image3 is not None:
        still_invest = check_template(log, image3, "invest", INVEST_TITLE_AREA, "invest_title_leave")
        if still_invest:
            log.warning("investment: still on invest screen after confirm")
            # 再点一次确认
            tap(log, *CONFIRM_TAP)
            time.sleep(2.0)

    log.info("investment: done")
    return 0


def _match_refresh(image) -> tuple[str | None, float]:
    """匹配刷新UI模板，返回 (模板名, 相似度)。"""
    from perception.templates import template_lib
    template_lib.reload()
    return template_lib.match(image, "invest", area=REFRESH_UI_AREA, similarity=0.80)


# ── 主入口 ──────────────────────────────────────────────────────────

def run(**kwargs) -> int:
    """对局内操作主入口。

    kwargs:
        investment_choice: 投资环境选项 1/2/3，默认2（测试用）
    """
    choice = kwargs.get("investment_choice", 2)  # TODO: 测试结束后改为外部输入
    log.info(f"gameplay: start, investment_choice={choice}")

    rc = select_investment(choice)
    if rc != 0:
        log.error(f"gameplay: investment failed (rc={rc})")
        return rc

    # TODO: 备战阶段（商店/角色选择）→ 战斗 → 结算
    log.info("gameplay: investment done, waiting for battle prep stage")
    return 0


if __name__ == "__main__":
    sys.exit(run())