from __future__ import annotations

import os

from .config import (
    CExamConfig,
    CExamTypeConfig,
    DEFAULT_FONT_CONFIGS,
    DigitConfig,
    ExportConfig,
    FontConfig,
    NoiseConfig,
    PageConfig,
    SquareConfig,
)
from .digit import DigitInfo
from .export import export_digit_pngs, export_noise_pngs, save_svg_and_pdf
from .geometry import Square
from .placement import place_c_exam_page
from .renderer import render_svg


def generate_page(
    page_cfg: PageConfig,
    squares: list[Square],
    digits: list[DigitInfo],
    filename: str,
    output_dir: str,
    font_size: int,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
) -> None:
    """单页管线：渲染 → 导出数字PNG → 导出噪声PNG → 保存SVG/PDF"""
    dwg = render_svg(page_cfg, squares, digits, filename, font_size)

    if export_cfg.enable_digit_export:
        export_digit_pngs(dwg, digits, export_cfg)

    if noise_cfg.enable:
        noise_font_folder = DEFAULT_FONT_CONFIGS["Times New Roman"].folder_name
        export_noise_pngs(
            dwg, squares, page_cfg, export_cfg, noise_cfg, noise_font_folder
        )

    save_svg_and_pdf(dwg, filename, output_dir)


def _generate_type(
    type_name: str,
    type_cfg: CExamTypeConfig,
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    digit_cfg: DigitConfig,
    font_cfg: FontConfig,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
    c_exam_dir: str,
) -> None:
    type_dir = os.path.join(c_exam_dir, type_name)
    for i in range(1, type_cfg.total_files + 1):
        filename = f"{type_name}_{i}.svg"
        result = place_c_exam_page(page_cfg, square_cfg, digit_cfg, font_cfg, type_cfg)
        generate_page(
            page_cfg,
            result.squares,
            result.digits,
            filename,
            type_dir,
            digit_cfg.font_size,
            export_cfg,
            noise_cfg,
        )


def generate_c_exam_pages(
    page_cfg: PageConfig,
    c_exam_cfg: CExamConfig,
    square_cfg: SquareConfig,
    digit_cfg: DigitConfig,
    font_cfg: FontConfig,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
    c_exam_dir: str,
) -> None:
    """按 C 题标准生成 4 类发挥目标物"""
    types = [
        ("type1_single", c_exam_cfg.type1_single, "单个正方形, 无数字, 无旋转"),
        ("type2_multi", c_exam_cfg.type2_multi, "多正方形组合, 无数字, 无旋转"),
        ("type3_digit", c_exam_cfg.type3_digit, "多正方形 + 数字编号, 无旋转"),
        ("type4_rotated", c_exam_cfg.type4_rotated, "单个正方形, 随机旋转"),
    ]

    for type_name, type_cfg, desc in types:
        print(f"  [cyan]{type_name}[/cyan]: {desc} ({type_cfg.total_files}张)")
        _generate_type(
            type_name,
            type_cfg,
            page_cfg,
            square_cfg,
            digit_cfg,
            font_cfg,
            export_cfg,
            noise_cfg,
            c_exam_dir,
        )
