"""感知层匹配原语。

封装 OpenCV 模板匹配、颜色比对、OCR（RapidOCR + ddddocr）为统一接口。
匹配函数返回数据而非布尔值，供上层结构化为 JSON 后交给 LLM 决策。
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from pathlib import Path

# Tesseract 路径（备用，当前主力为 RapidOCR + ddddocr）
_ROOT = Path(__file__).resolve().parent.parent
_TESSERACT_PATH = str(_ROOT / "tools" / "tesseract" / "tesseract.exe")

# ── 图像加载与裁剪 ──────────────────────────────────────────────────

def load_image(path: str | Path) -> np.ndarray:
    """加载图片为 BGR numpy 数组（OpenCV 惯用格式）。"""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"读不了图: {path}")
    return img


def crop(image: np.ndarray, area: tuple[int, int, int, int]) -> np.ndarray:
    """裁剪区域 (x1, y1, x2, y2)。坐标与截图一致，无需换算。"""
    x1, y1, x2, y2 = area
    return image[y1:y2, x1:x2]


def save_image(image: np.ndarray, path: str | Path) -> None:
    """存图，调试用。"""
    cv2.imwrite(str(path), image)


# ── 颜色匹配 ────────────────────────────────────────────────────────

def get_color(image: np.ndarray, area: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """取区域平均颜色 (B, G, R)。Alas 同名函数的逻辑。"""
    region = crop(image, area)
    mean = region.reshape(-1, 3).mean(axis=0)
    return tuple(int(v) for v in mean)


def color_similar(c1: tuple, c2: tuple, threshold: int = 30) -> bool:
    """两个颜色是否在阈值内相似。threshold 是各通道允许的偏差。"""
    return all(abs(a - b) <= threshold for a, b in zip(c1, c2))


# ── 模板匹配 ────────────────────────────────────────────────────────

def template_match(
    template: np.ndarray,
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    similarity: float = 0.85,
) -> tuple[float, tuple[int, int]]:
    """在 image 中找 template，返回 (相似度, 左上角坐标)。

    如果指定了 area，只在那个区域里找（缩小搜索范围提速）。
    用 TM_CCOEFF_NORMED（归一化相关系数），和 Alas 一致。

    返回值：
        similarity: 0~1，越高越像
        location: template 左上角在 image 中的坐标 (x, y)
    """
    search_area = crop(image, area) if area else image
    result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, sim, _, loc = cv2.minMaxLoc(result)

    # 如果在裁剪区域里找的，坐标要加回偏移
    if area:
        loc = (loc[0] + area[0], loc[1] + area[1])

    return float(sim), loc


def template_match_multi(
    template: np.ndarray,
    image: np.ndarray,
    similarity: float = 0.85,
    min_distance: int = 10,
) -> list[tuple[float, tuple[int, int]]]:
    """找所有匹配位置，返回 [(相似度, 坐标), ...]。

    用于商店格子、角色头像等"画面上可能出现多个同类元素"的场景。
    min_distance: 相邻结果的最小间距（像素），避免同一目标被重复检出。
    """
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= similarity)
    scores = result[locations]

    # 合并相近的结果
    points = list(zip(scores.tolist(), zip(locations[1].tolist(), locations[0].tolist())))
    if not points:
        return []

    # 按相似度降序排，贪心剔除太近的
    points.sort(key=lambda p: -p[0])
    kept: list[tuple[float, tuple[int, int]]] = []
    for score, pt in points:
        if all(abs(pt[0] - k[1][0]) + abs(pt[1] - k[1][1]) >= min_distance for k in kept):
            kept.append((score, pt))
    return kept


def match_binary(
    template: np.ndarray,
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    similarity: float = 0.85,
) -> tuple[float, tuple[int, int]]:
    """二值化后模板匹配。对光照变化更鲁棒。

    Alas 的 match_binary 逻辑：先把 template 和 image 都转灰度+Otsu 二值化，
    再做 matchTemplate。适合按钮文字、图标等高对比度元素。
    """
    search_area = crop(image, area) if area else image

    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, tpl_bin = cv2.threshold(tpl_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    img_gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
    _, img_bin = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    result = cv2.matchTemplate(img_bin, tpl_bin, cv2.TM_CCOEFF_NORMED)
    _, sim, _, loc = cv2.minMaxLoc(result)

    if area:
        loc = (loc[0] + area[0], loc[1] + area[1])

    return float(sim), loc


# ── OCR ─────────────────────────────────────────────────────────────

_pytesseract = None
_ddddocr_engine = None
_rapidocr_engine = None


def _get_tesseract():
    """懒加载 pytesseract，避免 import 时就要求装好。"""
    global _pytesseract
    if _pytesseract is None:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH
        _pytesseract = pytesseract
    return _pytesseract


def _get_ddddocr():
    """懒加载 ddddocr 数字特化引擎，优先使用 tools/ 下自包含版本。"""
    global _ddddocr_engine
    if _ddddocr_engine is None:
        import sys
        tools_dir = str(_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import ddddocr
        _ddddocr_engine = ddddocr.DdddOcr(show_ad=False)
    return _ddddocr_engine


def _get_rapidocr():
    """懒加载 RapidOCR 引擎，优先使用 tools/ 下自包含版本。"""
    global _rapidocr_engine
    if _rapidocr_engine is None:
        import sys
        tools_dir = str(_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from rapidocr_onnxruntime import RapidOCR
        _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def ocr(
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    lang: str = "chi_sim",
    whitelist: str | None = None,
    preprocess: str | None = None,
    scale: float = 1.0,
    psm: int | None = None,
) -> str:
    """Tesseract OCR，返回识别文本。备用接口，当前主力为 RapidOCR。

    Args:
        image: BGR 截图
        area: (x1,y1,x2,y2)，None 则整图
        lang: 语言包（chi_sim/eng/chi_sim+eng）
        whitelist: 只认这些字符
        preprocess: None/invert/binary/invert_binary
        scale: 放大倍数
        psm: 页面分割模式
    """
    region = crop(image, area) if area else image

    # 放大
    if scale > 1.0:
        region = cv2.resize(region, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_CUBIC)

    if preprocess:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        if preprocess == "invert":
            processed = cv2.bitwise_not(gray)
        elif preprocess == "binary":
            _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        elif preprocess == "invert_binary":
            inverted = cv2.bitwise_not(gray)
            _, processed = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        else:
            processed = gray
        pil = Image.fromarray(processed)
    else:
        rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)

    ts = _get_tesseract()
    config = ""
    if psm is not None:
        config += f"--psm {psm}"
    if whitelist:
        if config:
            config += " "
        config += f"-c tessedit_char_whitelist={whitelist}"
    text = ts.image_to_string(pil, lang=lang, config=config)
    return text.strip()


def ocr_digits(image: np.ndarray, area: tuple[int, int, int, int] | None = None) -> str:
    """数字 OCR，等价于 ocr_number()。"""
    return ocr_number(image, area)


def ocr_number(image: np.ndarray, area: tuple[int, int, int, int] | None = None) -> str:
    """数字特化 OCR（ddddocr引擎），用于层级数字、敌人难度等纯数字场景。

    ddddocr 对游戏UI大字体数字识别率远超 Tesseract，无需预处理。
    返回纯数字字符串，识别失败返回空字符串。
    """
    region = crop(image, area) if area else image
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    engine = _get_ddddocr()
    result = engine.classification(gray)
    return result.strip()


def ocr_rapid(
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
) -> list[tuple[list, str, float]]:
    """RapidOCR 全屏/区域识别，返回 [(box, text, conf), ...]。

    RapidOCR 自动检测文本位置和分行，适合中文密集场景（词条、位面等）。
    无需预设区域坐标即可全屏识别，也支持裁切区域识别。

    Args:
        image: 截图 BGR 数组
        area: (x1,y1,x2,y2)，指定区域；None 则整图

    Returns:
        list of [box, text, conf]：
        - box: 4个角点坐标 [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        - text: 识别文本
        - conf: 置信度 0~1
    """
    region = crop(image, area) if area else image
    engine = _get_rapidocr()
    result, _ = engine(region)
    return result if result else []


def ocr_rapid_text(
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
) -> str:
    """RapidOCR 区域识别，返回区域内所有文本拼接字符串。

    用于关键词检查等需要单区域文本的场景。
    """
    results = ocr_rapid(image, area=area)
    if not results:
        return ""
    return "".join(text for _, text, _ in results)


# ── 区域工具 ────────────────────────────────────────────────────────

def area_center(area: tuple[int, int, int, int]) -> tuple[int, int]:
    """区域中心点，用于点击。"""
    x1, y1, x2, y2 = area
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def area_offset(area: tuple[int, int, int, int], dx: int, dy: int) -> tuple[int, int, int, int]:
    """平移区域。"""
    x1, y1, x2, y2 = area
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)