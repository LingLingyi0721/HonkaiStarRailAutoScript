"""崩坏：星穹铁道 货币战争 BOSS 信息脚本。

前置条件：已通过 battle.py 进入词条首领一览界面（"下一步"）。

输出信息：
1. 当前段位（段位）+（层级） — 如 "当前段位：A8（50）"
2. 三位面文字 — 如 "第一位面：xxx"
3. 敌人难度+数值 — 如 "敌人难度：5"
4. 词条文字 — 1~4段，第4段需滑动补全
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/boss_info_screenshot.png")
ERROR_DIR = Path("log/error")

# 段位徽章区域（模板匹配）
RANK_BADGE_AREA = (72, 236, 108, 264)

# 层级数字区域（OCR识别）
LEVEL_AREA = (188, 303, 282, 374)

# 层级数字超过此阈值时默认段位为A8，跳过模板匹配
LEVEL_HIGH_THRESHOLD = 10
DEFAULT_HIGH_RANK = "A8"

# 三位面文字区域（y500-525）
DIMENSION1_AREA = (50, 500, 245, 525)    # 第一位面
DIMENSION2_AREA = (300, 500, 500, 525)   # 第二位面
DIMENSION3_AREA = (550, 500, 755, 525)   # 第三位面

# 敌人难度区域（文字+数值）
ENEMY_DIFFICULTY_AREA = (70, 640, 210, 670)

# 词条文字区域（1~4段，第4段可能需要滑动补全）
AFFIX_AREA = (220, 640, 765, 670)

# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = os.environ.get("HSR_LOG_FILE") or str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")

    logger = logging.getLogger("boss_info")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"日志文件: {log_file}")
    return logger


log = setup_logging()


# ── 错误快照 ───────────────────────────────────────────────────────

def snapshot_error(tag: str, error: str, context: dict, image: np.ndarray | None) -> None:
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if image is not None:
        shot_path = ERROR_DIR / f"{ts}_{tag}.png"
        cv2.imwrite(str(shot_path), image)
        log.error(f"错误快照已保存: {shot_path}")

    log_path = ERROR_DIR / f"{ts}_{tag}.log"
    lines = [f"时间: {ts}", f"标签: {tag}", f"错误: {error}"]
    for k, v in context.items():
        lines.append(f"{k}: {v}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.error(f"错误日志已保存: {log_path}")


# ── 设备操作 ───────────────────────────────────────────────────────

def ensure_device() -> None:
    from tools.devkit import ensure_connected
    state = ensure_connected()
    log.info(f"设备连接: {state}")


def screenshot() -> np.ndarray | None:
    from tools.devkit import screencap_png
    try:
        png_bytes = screencap_png()
        image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            log.error("截图失败: PNG 解码失败")
            return None
        log.info("截图成功")
        CACHE_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(CACHE_SCREENSHOT), image)
        return image
    except Exception as e:
        log.error(f"截图失败: {e}")
        return None


def tap(x: int, y: int) -> None:
    from tools.devkit import tap as _tap
    _tap(x, y)
    log.info(f"点击 ({x}, {y})")


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
    from tools.devkit import swipe as _swipe
    _swipe(x1, y1, x2, y2, duration_ms)
    log.info(f"滑动 ({x1},{y1}) -> ({x2},{y2})")


# ── 信息提取 ───────────────────────────────────────────────────────

def get_rank_level(image: np.ndarray) -> dict | None:
    """识别当前段位和层级，返回字典 {rank, level}。

    层级数字超过 LEVEL_HIGH_THRESHOLD 时默认段位为A8，跳过模板匹配。
    """
    from perception.matcher import ocr
    from perception.templates import template_lib

    # 先识别层级数字
    level_text = ocr(image, area=LEVEL_AREA, lang="eng",
                     whitelist="0123456789",
                     preprocess=None, scale=1.0, psm=6)
    level_text = level_text.strip()

    if not level_text or not level_text.isdigit():
        log.warning("层级数字识别失败: %s" % repr(level_text))
        return None

    level_num = int(level_text)

    # 层级超过阈值则默认A8，否则模板匹配段位徽章
    if level_num > LEVEL_HIGH_THRESHOLD:
        rank_name = DEFAULT_HIGH_RANK
        log.info("段位: %s (层级%d>%d, 默认判定)" % (rank_name, level_num, LEVEL_HIGH_THRESHOLD))
    else:
        template_lib.reload()
        rank_name, rank_sim = template_lib.match(image, "rank", area=RANK_BADGE_AREA)
        if rank_name is None:
            log.warning("段位徽章匹配失败 (最高相似度=%.4f)" % rank_sim)
            return None
        log.info("段位: %s (相似度=%.4f)" % (rank_name, rank_sim))

    log.info("层级: %s" % level_text)
    return {"rank": rank_name, "level": level_text}


def get_dimensions(image: np.ndarray) -> dict:
    """识别三位面文字，返回 {dimension1, dimension2, dimension3}。"""
    from perception.matcher import ocr

    results = {}
    areas = [
        ("dimension1", DIMENSION1_AREA),
        ("dimension2", DIMENSION2_AREA),
        ("dimension3", DIMENSION3_AREA),
    ]

    for name, area in areas:
        text = ocr(image, area=area, lang="chi_sim+eng",
                   preprocess=None, scale=1.0, psm=6)
        text = text.strip()
        results[name] = text
        log.info(f"{name}: {text if text else '(空)'}")

    return results


def get_enemy_difficulty(image: np.ndarray) -> str | None:
    """识别敌人难度+数值，返回如 '5' 或 '敌人难度：5' 中的数值部分。

    区域 x70-210, y640-670 包含"敌人难度"文字和数值。
    先尝试整体识别，提取数值；如果文字干扰大，用数字白名单只认数字。
    """
    from perception.matcher import ocr

    # 先整体识别（文字+数值）
    full_text = ocr(image, area=ENEMY_DIFFICULTY_AREA, lang="chi_sim+eng",
                    preprocess=None, scale=1.0, psm=6)
    log.info(f"敌人难度区域原始识别: {repr(full_text)}")

    # 从识别结果中提取数字
    import re
    numbers = re.findall(r'\d+', full_text)
    if numbers:
        difficulty = numbers[-1]  # 取最后一个数字（难度数值通常在文字后面）
        log.info(f"敌人难度: {difficulty}")
        return difficulty

    # 如果整体识别没提取到数字，用数字白名单再试
    digits_text = ocr(image, area=ENEMY_DIFFICULTY_AREA, lang="eng",
                      whitelist="0123456789",
                      preprocess=None, scale=2.0, psm=6)
    digits_text = digits_text.strip()
    if digits_text and digits_text.isdigit():
        log.info(f"敌人难度(数字白名单): {digits_text}")
        return digits_text

    log.warning("敌人难度识别失败")
    return None


def get_affixes(image: np.ndarray) -> list[str]:
    """识别词条文字，返回词条列表（1~4段）。

    区域 x220-765, y640-670 包含1~4段词条文字，每段前面有一个乱码标记。
    如果存在第4段，先确认前三段内容，然后从此区域往左滑动一次，再识别补全第4段。
    """
    from perception.matcher import ocr

    # 第一次识别
    text = ocr(image, area=AFFIX_AREA, lang="chi_sim+eng",
               preprocess=None, scale=1.0, psm=6)
    log.info(f"词条区域原始识别: {repr(text)}")

    # 分割词条：乱码字符作为分隔标志，后面接文字内容
    # 乱码通常是特殊符号、方块、问号等非中文非数字字符
    import re
    # 用非中文、非数字、非字母的连续字符作为分隔
    parts = re.split(r'[^\u4e00-\u9fff\w]+', text)
    # 过滤空字符串
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        log.warning("词条识别失败：未识别到任何内容")
        return []

    log.info(f"词条分割结果: {parts} (共{len(parts)}段)")

    # 如果有4段或以上，需要滑动补全第4段
    if len(parts) >= 4:
        log.info("检测到4段词条，执行滑动补全第4段")
        # 先确认前三段
        confirmed = parts[:3]
        log.info(f"前三段已确认: {confirmed}")

        # 从词条区域往左滑动（让第4段完整显示）
        # 滑动起点：区域右侧，终点：区域左侧，同一y高度
        x1, y1, x2, y2 = AFFIX_AREA
        mid_y = (y1 + y2) // 2
        swipe(x2 - 20, mid_y, x1 + 20, mid_y, duration_ms=500)
        time.sleep(1.0)

        # 滑动后重新截图并识别
        new_image = screenshot()
        if new_image is not None:
            new_text = ocr(new_image, area=AFFIX_AREA, lang="chi_sim+eng",
                           preprocess=None, scale=1.0, psm=6)
            log.info(f"滑动后词条区域识别: {repr(new_text)}")
            new_parts = re.split(r'[^\u4e00-\u9fff\w]+', new_text)
            new_parts = [p.strip() for p in new_parts if p.strip()]
            log.info(f"滑动后词条分割结果: {new_parts}")

            # 取滑动后识别到的最后一个有效段作为第4段
            if new_parts:
                # 滑动后第4段应该出现在前面位置了
                # 取第一个或最后一个非空段作为补全
                fourth = new_parts[0] if len(new_parts) == 1 else new_parts[-1]
                confirmed.append(fourth)
                log.info(f"第4段补全: {fourth}")
            else:
                confirmed.append(parts[3])  # 滑动后识别失败，用原始结果
                log.warning("滑动后识别失败，使用原始第4段结果")
        else:
            confirmed.append(parts[3])  # 截图失败，用原始结果
            log.warning("滑动后截图失败，使用原始第4段结果")

        return confirmed

    return parts


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 BOSS 信息识别")
    log.info("=" * 50)

    try:
        ensure_device()
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    image = screenshot()
    if image is None:
        log.error("截图失败，无法继续")
        return 1

    # ── 1. 段位和层级 ──
    log.info("-" * 30)
    log.info("步骤1: 段位和层级")
    log.info("-" * 30)

    rank_info = get_rank_level(image)
    if rank_info:
        rank_str = f"当前段位：{rank_info['rank']}（{rank_info['level']}）"
        log.info(rank_str)
    else:
        rank_str = "当前段位：识别失败"
        log.warning(rank_str)

    # ── 2. 三位面文字 ──
    log.info("-" * 30)
    log.info("步骤2: 三位面")
    log.info("-" * 30)

    dim_info = get_dimensions(image)
    dim1_str = f"第一位面：{dim_info['dimension1']}" if dim_info['dimension1'] else "第一位面：(空)"
    dim2_str = f"第二位面：{dim_info['dimension2']}" if dim_info['dimension2'] else "第二位面：(空)"
    dim3_str = f"第三位面：{dim_info['dimension3']}" if dim_info['dimension3'] else "第三位面：(空)"
    log.info(dim1_str)
    log.info(dim2_str)
    log.info(dim3_str)

    # ── 3. 敌人难度 ──
    log.info("-" * 30)
    log.info("步骤3: 敌人难度")
    log.info("-" * 30)

    difficulty = get_enemy_difficulty(image)
    if difficulty:
        diff_str = f"敌人难度：{difficulty}"
        log.info(diff_str)
    else:
        diff_str = "敌人难度：识别失败"
        log.warning(diff_str)

    # ── 4. 词条文字 ──
    log.info("-" * 30)
    log.info("步骤4: 词条")
    log.info("-" * 30)

    affixes = get_affixes(image)
    if affixes:
        for i, affix in enumerate(affixes, 1):
            log.info(f"词条{i}：{affix}")
    else:
        log.warning("词条识别失败")

    # ── 汇总输出 ──
    log.info("=" * 50)
    log.info("BOSS 信息汇总")
    log.info("=" * 50)
    if rank_info:
        log.info(f"当前段位：{rank_info['rank']}（{rank_info['level']}）")
    log.info(dim1_str)
    log.info(dim2_str)
    log.info(dim3_str)
    if difficulty:
        log.info(f"敌人难度：{difficulty}")
    for i, affix in enumerate(affixes, 1):
        log.info(f"词条{i}：{affix}")

    return 0


if __name__ == "__main__":
    sys.exit(run())