"""模板匹配库。

自动扫描 image/ 目录，按子文件夹分类加载模板图片。
用户只需在对应子文件夹内放置模板图片即可，无需改代码。

目录结构示例：
    image/
        rank/       # 段位徽章模板 (A0.png, A1.png, ... A8.png)
        button/     # 按钮模板
        icon/       # 图标模板
        ...

用法：
    from perception.templates import template_lib

    # 匹配段位徽章
    name, sim = template_lib.match(image, "rank", area=(75, 235, 103, 252))
    # 返回 ("A7", 0.95) 或 (None, 0)

    # 匹配所有超过阈值的模板
    results = template_lib.match_all(image, "rank", area=(75, 235, 103, 252))
    # 返回 [("A7", 0.95), ("A8", 0.72)]
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

from perception.matcher import template_match, crop

_ROOT = Path(__file__).resolve().parent.parent / "image"


class TemplateLib:
    """模板库：自动扫描 image/ 目录，按子文件夹分类加载模板。"""

    def __init__(self, root: Path | str = _ROOT):
        self.root = Path(root)
        self.categories: dict[str, dict[str, np.ndarray]] = {}
        self._scan()

    def _scan(self) -> None:
        """扫描 image/ 目录，加载所有 .png 模板。"""
        self.categories.clear()
        if not self.root.exists():
            return
        for subdir in sorted(self.root.iterdir()):
            if not subdir.is_dir():
                continue
            category = subdir.name
            templates: dict[str, np.ndarray] = {}
            for img_file in sorted(subdir.glob("*.png")):
                name = img_file.stem
                img = cv2.imread(str(img_file), cv2.IMREAD_COLOR)
                if img is not None:
                    templates[name] = img
            if templates:
                self.categories[category] = templates

    def reload(self) -> None:
        """重新扫描目录，加载新增的模板。"""
        self._scan()

    def list_categories(self) -> list[str]:
        """返回所有类别名。"""
        return list(self.categories.keys())

    def list_templates(self, category: str) -> list[str]:
        """返回某类别下所有模板名。"""
        return list(self.categories.get(category, {}).keys())

    def match(
        self,
        image: np.ndarray,
        category: str,
        area: tuple[int, int, int, int] | None = None,
        similarity: float = 0.80,
    ) -> tuple[str | None, float]:
        """在指定区域匹配该类别下所有模板，返回最佳匹配。

        Args:
            image: 截图 BGR 数组
            category: 类别名（对应 image/ 下的子文件夹名）
            area: (x1,y1,x2,y2) 搜索区域；None 则全图
            similarity: 最低相似度阈值

        Returns:
            (template_name, similarity) 或 (None, 0)
        """
        if category not in self.categories:
            return None, 0.0

        best_name: str | None = None
        best_sim = 0.0

        for name, template in self.categories[category].items():
            sim, _ = template_match(template, image, area=area, similarity=0.0)
            if sim > best_sim:
                best_name, best_sim = name, sim

        if best_sim < similarity:
            return None, best_sim
        return best_name, best_sim

    def match_all(
        self,
        image: np.ndarray,
        category: str,
        area: tuple[int, int, int, int] | None = None,
        similarity: float = 0.80,
    ) -> list[tuple[str, float]]:
        """返回所有匹配度超过阈值的模板，按相似度降序排列。

        Returns:
            [(template_name, similarity), ...]
        """
        if category not in self.categories:
            return []

        results: list[tuple[str, float]] = []
        for name, template in self.categories[category].items():
            sim, _ = template_match(template, image, area=area, similarity=0.0)
            if sim >= similarity:
                results.append((name, sim))

        results.sort(key=lambda x: -x[1])
        return results


# 全局单例，import 时自动加载
template_lib = TemplateLib()