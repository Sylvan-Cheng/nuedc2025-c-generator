from __future__ import annotations

import os
import shutil
import sys
from collections import Counter
from pathlib import Path

from rich import print
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
from .placement import _count_overlaps, place_squares
from .yolo_export import (
    generate_yolo_dataset,
    init_yolo_dataset_dir,
)

DIFFICULTY_NAMES = {
    Difficulty.EASY: "难度0 (简单: 2-4个, 无旋转, 无重叠, 均匀分布)",
    Difficulty.MEDIUM: "难度1 (中等: 3-4个, 无旋转, 至少1对重叠, 均匀分布)",
    Difficulty.HARD: "难度2 (困难: 3-5个, 随机旋转, 可重叠, 均匀分布)",
}


def main() -> None:
    try:
        config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        _run(config_path)
    except KeyboardInterrupt:
        print("\n[yellow]用户取消[/yellow]")


def _run(config_path: Path | None = None) -> None:
    raw = load_config(config_path)

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

    _clear_output_dir(global_cfg.output_dir)
    print(f"[cyan]输出目录: {_display_path(global_cfg.output_dir)}[/cyan]")
    print("[cyan]已清空输出目录[/cyan]")
    print()

    if yolo_cfg.enable:
        init_yolo_dataset_dir(yolo_cfg, yolo_dataset_dir)

    if basic_cfg.enable:
        print("[bold cyan]=== 生成基本目标物 ===[/bold cyan]")
        generate_basic_targets(page_cfg, basic_cfg, basic_target_dir)
        print()

    if ext_cfg.enable and ext_cfg.total_files > 0:
        print(
            f"[bold cyan]=== 生成练习用目标物 - {DIFFICULTY_NAMES[ext_cfg.difficulty]} ===[/bold cyan]"
        )
        print(f"[cyan]输出: {_display_path(extended_target_dir)}[/cyan]")

        count_stats: Counter[int] = Counter()
        overlap_stats: Counter[int] = Counter()

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
                "[green]生成练习用目标物...",
                total=ext_cfg.total_files,
            )
            for i in range(1, ext_cfg.total_files + 1):
                filename = f"{i}.svg"
                result = place_squares(
                    page_cfg, ext_cfg, font_cfg, generate_digits=True
                )
                count_stats[len(result.squares)] += 1
                overlap_stats[_count_overlaps(result.squares)] += 1
                generate_page(
                    page_cfg,
                    result.squares,
                    result.digits,
                    filename,
                    extended_target_dir,
                    ext_cfg.digit.font_size,
                    export_cfg,
                    noise_cfg,
                )
                progress.update(task, advance=1)

        print(f"[bold green]完成: {ext_cfg.total_files} 组 SVG/PDF[/bold green]")
        print(f"[cyan]数量分布: {_format_counter(count_stats, '个')}[/cyan]")
        print(f"[cyan]重叠分布: {_format_counter(overlap_stats, '对')}[/cyan]")

    print()

    if c_exam_cfg.enable:
        print("[bold cyan]=== 生成 C 题标准发挥目标物 ===[/bold cyan]")
        generate_c_exam_pages(
            page_cfg,
            c_exam_cfg,
            ext_cfg.square,
            ext_cfg.digit,
            font_cfg,
            export_cfg,
            noise_cfg,
            c_exam_dir,
            ext_cfg.overlap,
        )
        print()

    print("[bold green]图案文件生成完毕![/bold green]")

    if yolo_cfg.enable:
        print()
        generate_yolo_dataset(yolo_cfg, yolo_dataset_dir, augment_cfg, font_cfg)

    print()
    print("[bold green]全部任务完成![/bold green]")
    print(
        "[cyan]如果觉得有用，欢迎 Star "
        "https://github.com/Sylvan-Cheng/nuedc2025-c-generator[/cyan]"
    )


def _format_counter(counter: Counter[int], suffix: str) -> str:
    return ", ".join(
        f"{key}{suffix}={counter[key]}" for key in sorted(counter)
    )


def _display_path(path: str) -> str:
    return os.path.normpath(path)


def _clear_output_dir(output_dir: str) -> None:
    if not output_dir or not output_dir.strip():
        raise ValueError("global.output_dir must not be empty")

    target = Path(output_dir).expanduser().resolve()
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    root = Path(target.anchor).resolve()

    protected = {cwd, home, root}
    if target in protected:
        raise ValueError(f"refusing to clear protected output directory: {target}")

    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


if __name__ == "__main__":
    main()
