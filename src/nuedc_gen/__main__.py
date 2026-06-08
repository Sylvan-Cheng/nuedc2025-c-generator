from __future__ import annotations

import os

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .basic_target import generate_basic_targets
from .config import (
    BasicTargetConfig,
    CExamConfig,
    CExamTypeConfig,
    DEFAULT_FONT_CONFIGS,
    DigitConfig,
    Difficulty,
    ExportConfig,
    ExtendedTargetConfig,
    FontConfig,
    NoiseConfig,
    PageConfig,
    SquareConfig,
    load_config,
)
from .export import export_digit_pngs, export_noise_pngs, save_svg_and_pdf
from .placement import PlacementResult, place_c_exam_page, place_squares
from .renderer import render_svg

DIFFICULTY_NAMES = {
    Difficulty.EASY: "难度0 (简单: 1-3个, 无旋转, 无重叠, 平均分布)",
    Difficulty.MEDIUM: "难度1 (中等: 2-4个, 无旋转, 最多1对重叠)",
    Difficulty.HARD: "难度2 (困难: 3-5个, 随机旋转, 可重叠)",
}


def _render_and_save(
    page_cfg: PageConfig,
    result: PlacementResult,
    filename: str,
    output_dir: str,
    font_size: int,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
) -> None:
    """统一的 渲染 → 导出 → 保存 流程"""
    dwg = render_svg(page_cfg, result.squares, result.digits, filename, font_size)

    if export_cfg.enable_digit_export:
        export_digit_pngs(dwg, result.digits, page_cfg, export_cfg)

    if noise_cfg.enable:
        noise_font_folder = DEFAULT_FONT_CONFIGS["Times New Roman"].folder_name
        export_noise_pngs(dwg, result.squares, page_cfg, export_cfg, noise_cfg, noise_font_folder)

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
    """为 C 题标准模式生成某一类型的全部图片"""
    type_dir = os.path.join(c_exam_dir, type_name)
    for i in range(1, type_cfg.total_files + 1):
        filename = f"{type_name}_{i}.svg"
        result = place_c_exam_page(page_cfg, square_cfg, digit_cfg, font_cfg, type_cfg)
        _render_and_save(page_cfg, result, filename, type_dir, digit_cfg.font_size, export_cfg, noise_cfg)


def generate_c_exam(
    page_cfg: PageConfig,
    c_exam_cfg: CExamConfig,
    square_cfg: SquareConfig,
    digit_cfg: DigitConfig,
    font_cfg: FontConfig,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
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
            type_name, type_cfg,
            page_cfg, square_cfg, digit_cfg, font_cfg,
            export_cfg, noise_cfg,
            c_exam_cfg.output_dir,
        )


def main() -> None:
    raw = load_config()

    page_cfg = PageConfig.from_raw(raw)
    basic_cfg = BasicTargetConfig.from_raw(raw)
    ext_cfg = ExtendedTargetConfig.from_raw(raw)
    export_cfg = ExportConfig.from_raw(raw)
    font_cfg = FontConfig.from_raw(raw)
    noise_cfg = NoiseConfig.from_raw(raw)
    c_exam_cfg = CExamConfig.from_raw(raw)

    # 生成基本目标物（圆形、三角形、正方形）
    if basic_cfg.enable:
        print("[bold cyan]=== 生成基本目标物 ===[/bold cyan]")
        generate_basic_targets(page_cfg, basic_cfg)
        print()

    # C 题标准模式：恰好 4 类发挥目标物
    if c_exam_cfg.enable:
        print("[bold cyan]=== 生成 C 题标准发挥目标物 ===[/bold cyan]")
        generate_c_exam(
            page_cfg, c_exam_cfg,
            ext_cfg.square, ext_cfg.digit, font_cfg,
            export_cfg, noise_cfg,
        )
        print()

    # 批量训练模式
    if ext_cfg.enable and ext_cfg.total_files > 0:
        print(f"[bold cyan]=== 生成发挥目标物 - {DIFFICULTY_NAMES[ext_cfg.difficulty]} ===[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            expand=True,
        ) as progress:
            task = progress.add_task(
                "[green]生成发挥目标物...",
                total=ext_cfg.total_files,
            )
            for i in range(1, ext_cfg.total_files + 1):
                filename = f"{i}.svg"
                result = place_squares(page_cfg, ext_cfg, font_cfg, generate_digits=True)
                _render_and_save(
                    page_cfg, result, filename,
                    ext_cfg.output_dir, ext_cfg.digit.font_size,
                    export_cfg, noise_cfg,
                )
                progress.update(task, advance=1)

    print("[bold green]所有文件生成完毕![/bold green]")


if __name__ == "__main__":
    main()
