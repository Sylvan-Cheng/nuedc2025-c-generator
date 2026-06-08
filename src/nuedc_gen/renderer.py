from __future__ import annotations

import math

import svgwrite

from .config import PageConfig
from .digit import DigitInfo
from .geometry import ShapeType, Square


def create_background(page_cfg: PageConfig, filename: str) -> svgwrite.Drawing:
    dwg = svgwrite.Drawing(
        filename,
        size=(f"{page_cfg.width_mm}mm", f"{page_cfg.height_mm}mm"),
        viewBox=f"0 0 {page_cfg.width_mm} {page_cfg.height_mm}",
    )
    dwg.add(dwg.rect(
        insert=(0, 0),
        size=(page_cfg.width_mm, page_cfg.height_mm),
        fill="black",
        stroke="none",
    ))
    dwg.add(dwg.rect(
        insert=(page_cfg.margin, page_cfg.margin),
        size=(
            page_cfg.width_mm - 2 * page_cfg.margin,
            page_cfg.height_mm - 2 * page_cfg.margin,
        ),
        fill="white",
        stroke="none",
    ))
    return dwg


def add_squares_to_svg(
    dwg: svgwrite.Drawing,
    squares: list[Square],
) -> None:
    for sq in squares:
        elem = dwg.rect(
            insert=(0, 0),
            size=(sq.size, sq.size),
            fill="black",
            stroke="none",
        )
        elem.attribs["transform"] = (
            f"translate({sq.x} {sq.y}) rotate({sq.angle} {sq.size / 2} {sq.size / 2})"
        )
        dwg.add(elem)


def add_digits_to_svg(
    dwg: svgwrite.Drawing,
    digits: list[DigitInfo],
    font_size: int = 30,
) -> None:
    for info in digits:
        text_elem = dwg.text(
            str(info.digit),
            insert=(info.size / 2, info.size / 2),
            font_family=info.css_font,
            font_size=font_size,
            font_weight="bold" if info.use_bold else "normal",
            text_anchor="middle",
            fill="white",
        )
        text_elem.attribs["dy"] = "0.35em"
        text_elem.attribs["transform"] = (
            f"translate({info.center_x - info.size / 2} {info.center_y - info.size / 2}) "
            f"rotate({info.rotation} {info.size / 2} {info.size / 2})"
        )
        dwg.add(text_elem)


def render_svg(
    page_cfg: PageConfig,
    squares: list[Square],
    digits: list[DigitInfo],
    filename: str,
    font_size: int = 30,
) -> svgwrite.Drawing:
    dwg = create_background(page_cfg, filename)
    add_squares_to_svg(dwg, squares)
    add_digits_to_svg(dwg, digits, font_size)
    return dwg


def add_circle_to_svg(
    dwg: svgwrite.Drawing,
    cx: float,
    cy: float,
    diameter: float,
) -> None:
    """绘制圆形（黑色实心）"""
    elem = dwg.circle(
        center=(cx, cy),
        r=diameter / 2,
        fill="black",
        stroke="none",
    )
    dwg.add(elem)


def add_triangle_to_svg(
    dwg: svgwrite.Drawing,
    cx: float,
    cy: float,
    size: float,
) -> None:
    """绘制等边三角形（黑色实心，底边水平）"""
    h = size * math.sqrt(3) / 2
    points = [
        (cx - size / 2, cy + h / 3),
        (cx + size / 2, cy + h / 3),
        (cx, cy - 2 * h / 3),
    ]
    elem = dwg.polygon(
        points=points,
        fill="black",
        stroke="none",
    )
    dwg.add(elem)


def render_basic_target(
    page_cfg: PageConfig,
    shape_type: ShapeType,
    size: float,
    filename: str,
) -> svgwrite.Drawing:
    """渲染基本目标物（单个图形居中，无数字）"""
    dwg = create_background(page_cfg, filename)

    cx = page_cfg.width_mm / 2
    cy = page_cfg.height_mm / 2

    if shape_type == ShapeType.SQUARE:
        x = cx - size / 2
        y = cy - size / 2
        elem = dwg.rect(
            insert=(x, y),
            size=(size, size),
            fill="black",
            stroke="none",
        )
        dwg.add(elem)
    elif shape_type == ShapeType.CIRCLE:
        add_circle_to_svg(dwg, cx, cy, size)
    elif shape_type == ShapeType.TRIANGLE:
        add_triangle_to_svg(dwg, cx, cy, size)

    return dwg
