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
    AugmentConfig,
    BasicTargetConfig,
    CExamConfig,
    Difficulty,
    ExportConfig,
    ExtendedTargetConfig,
    FontConfig,
    GlobalConfig,
    NoiseConfig,
    PageConfig,
    YoloExportConfig,
    load_config,
)
from .page_generator import generate_c_exam_pages, generate_page
from .placement import place_squares
from .yolo_export import (
    cleanup_yolo_tmp,
    generate_yolo_dataset,
    init_yolo_dataset_dir,
)

DIFFICULTY_NAMES = {
    Difficulty.EASY: "难度0 (简单: 1-3个, 无旋转, 无重叠, 平均分布)",
    Difficulty.MEDIUM: "难度1 (中等: 2-4个, 无旋转, 最多1对重叠)",
    Difficulty.HARD: "难度2 (困难: 3-5个, 随机旋转, 可重叠)",
}


def main() -> None:
    raw = load_config()

    global_cfg = GlobalConfig.from_raw(raw)
    page_cfg = PageConfig.from_raw(raw)
    basic_cfg = BasicTargetConfig.from_raw(raw)
    ext_cfg = ExtendedTargetConfig.from_raw(raw)
    export_cfg = ExportConfig.from_raw(raw)
    font_cfg = FontConfig.from_raw(raw)
    augment_cfg = AugmentConfig.from_raw(raw)
    noise_cfg = NoiseConfig.from_raw(raw)
    c_exam_cfg = CExamConfig.from_raw(raw)
    yolo_cfg = YoloExportConfig.from_raw(raw)

    basic_target_dir = os.path.join(global_cfg.output_dir, "basic_targets")
    c_exam_dir = os.path.join(global_cfg.output_dir, "c_exam")
    extended_target_dir = global_cfg.output_dir
    yolo_dataset_dir = os.path.join(global_cfg.output_dir, "yolo_dataset")

    if yolo_cfg.enable:
        print("[bold cyan]=== 初始化YOLO数据集目录 ===[/bold cyan]")
        init_yolo_dataset_dir(yolo_cfg, yolo_dataset_dir)
        print()

    if basic_cfg.enable:
        print("[bold cyan]=== 生成基本目标物 ===[/bold cyan]")
        generate_basic_targets(page_cfg, basic_cfg, basic_target_dir)
        print()

    if c_exam_cfg.enable:
        print("[bold cyan]=== 生成 C 题标准发挥目标物 ===[/bold cyan]")
        generate_c_exam_pages(
            page_cfg, c_exam_cfg,
            ext_cfg.square, ext_cfg.digit, font_cfg,
            export_cfg, noise_cfg,
            c_exam_dir,
        )
        print()

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
                generate_page(
                    page_cfg, result.squares, result.digits, filename,
                    extended_target_dir, ext_cfg.digit.font_size,
                    export_cfg, noise_cfg,
                )
                progress.update(task, advance=1)

    print("[bold green]所有文件生成完毕![/bold green]")

    if yolo_cfg.enable:
        print()
        generate_yolo_dataset(yolo_cfg, yolo_dataset_dir, augment_cfg, font_cfg)


if __name__ == "__main__":
    main()
