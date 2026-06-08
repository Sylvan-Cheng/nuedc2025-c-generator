from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import FontConfig, FontSelector


@dataclass(frozen=True)
class DigitInfo:
    """数字信息 — 领域数据 + 渲染数据合并（保持向后兼容）"""
    digit: int
    center_x: float
    center_y: float
    rotation: float
    size: float
    css_font: str
    font_folder_name: str
    use_bold: bool


def _get_available_digits(used_digits: set[int]) -> set[int]:
    """内部：获取可用数字集合（6/9 互斥）"""
    all_digits = set(range(10))
    if 6 in used_digits and 9 in used_digits:
        return set()
    if 6 in used_digits:
        return all_digits - used_digits - {9}
    if 9 in used_digits:
        return all_digits - used_digits - {6}
    return all_digits - used_digits


def _does_digit_overlap(
    new_center: tuple[float, float],
    existing_centers: list[tuple[float, float]],
    threshold: float = 40,
) -> bool:
    """内部：检查数字中心是否重叠"""
    nx, ny = new_center
    for cx, cy in existing_centers:
        if math.hypot(nx - cx, ny - cy) < threshold:
            return True
    return False


def assign_digit(
    center_x: float,
    center_y: float,
    size: float,
    rotation: float,
    used_digits: set[int],
    digit_centers: list[tuple[float, float]],
    font_cfg: FontConfig,
    overlap_threshold: float = 40,
) -> DigitInfo | None:
    """为一个正方形分配数字。返回 None 表示无法分配（数字用完或重叠）"""
    available = _get_available_digits(used_digits)
    if not available:
        return None

    if _does_digit_overlap((center_x, center_y), digit_centers, overlap_threshold):
        return None

    digit = random.choice(list(available))

    _font_name, font_entry = FontSelector.choose_font(font_cfg)
    use_bold = FontSelector.should_use_bold(font_cfg)
    css_font = FontSelector.get_css_font(font_entry, use_bold)
    folder_name = FontSelector.get_folder_name(font_entry, use_bold)

    return DigitInfo(
        digit=digit,
        center_x=center_x,
        center_y=center_y,
        rotation=rotation,
        size=size,
        css_font=css_font,
        font_folder_name=folder_name,
        use_bold=use_bold,
    )
