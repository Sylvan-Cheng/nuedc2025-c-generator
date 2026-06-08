from __future__ import annotations

import os

from .config import BasicTargetConfig, PageConfig
from .export import save_svg_and_pdf
from .geometry import ShapeType
from .renderer import render_basic_target


def generate_basic_targets(
    page_cfg: PageConfig,
    basic_cfg: BasicTargetConfig,
) -> None:
    """生成三种基本目标物：圆形、三角形、正方形。

    每种图形生成 min_size ~ max_size 范围内，以 step 为间隔的所有尺寸。
    默认：100mm ~ 160mm，间隔 5mm，共 13 个尺寸 × 3 种图形 = 39 个文件。
    """
    shapes = [ShapeType.CIRCLE, ShapeType.TRIANGLE, ShapeType.SQUARE]
    sizes = range(basic_cfg.min_size_mm, basic_cfg.max_size_mm + 1, basic_cfg.step_mm)

    total = len(shapes) * len(sizes)
    count = 0

    for shape in shapes:
        shape_dir = os.path.join(basic_cfg.output_dir, shape.value)
        os.makedirs(os.path.join(shape_dir, "svg"), exist_ok=True)
        os.makedirs(os.path.join(shape_dir, "pdf"), exist_ok=True)

        for size in sizes:
            count += 1
            filename = f"{shape.value}_{size}mm.svg"
            dwg = render_basic_target(page_cfg, shape, size, filename)
            save_svg_and_pdf(dwg, filename, shape_dir)
            print(f"[{count}/{total}] {shape.value} {size}mm")

    print(f"\n[bold green]基本目标物生成完毕! 共 {count} 个文件[/bold green]")
