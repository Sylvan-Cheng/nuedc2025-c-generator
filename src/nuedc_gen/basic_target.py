from __future__ import annotations

import os

from rich import print
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .config import BasicTargetConfig, PageConfig
from .export import save_svg_and_pdf
from .geometry import ShapeType
from .renderer import render_basic_target


def generate_basic_targets(
    page_cfg: PageConfig,
    basic_cfg: BasicTargetConfig,
    output_dir: str,
) -> None:
    shapes = [ShapeType.CIRCLE, ShapeType.TRIANGLE, ShapeType.SQUARE]
    sizes = range(basic_cfg.min_size_mm, basic_cfg.max_size_mm + 1, basic_cfg.step_mm)

    total = len(shapes) * len(sizes)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        expand=True,
    ) as progress:
        task = progress.add_task("[green]生成基本目标物...", total=total)

        for shape in shapes:
            shape_dir = os.path.join(output_dir, shape.value)
            os.makedirs(os.path.join(shape_dir, "svg"), exist_ok=True)
            os.makedirs(os.path.join(shape_dir, "pdf"), exist_ok=True)

            for size in sizes:
                filename = f"{shape.value}_{size}mm.svg"
                dwg = render_basic_target(page_cfg, shape, size, filename)
                save_svg_and_pdf(dwg, filename, shape_dir)
                progress.advance(task)

    print(f"[bold green]基本目标物生成完毕! 共 {total} 个文件[/bold green]")
