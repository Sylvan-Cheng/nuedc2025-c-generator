from __future__ import annotations

import os
import random
import re

import resvg_py
import svgwrite
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

from .config import ExportConfig, NoiseConfig, PageConfig
from .digit import DigitInfo
from .geometry import Square, rectangle_overlap_area

# 匹配 SVG 根元素上的 viewBox 属性（容忍空格变化）
_VIEWBOX_RE = re.compile(r'(<svg[^>]*\bviewBox=")([^"]*)(")', re.DOTALL)
# 匹配 width 或 height 属性上的 mm 单位后缀
_UNIT_RE = re.compile(r'\b(width|height)="([\d.]+)mm"')


def crop_svg_to_png(
    full_svg_data: str,
    viewbox_x: float,
    viewbox_y: float,
    viewbox_w: float,
    viewbox_h: float,
    output_path: str,
    output_px: int = 60,
) -> bool:
    new_vb = f"{viewbox_x} {viewbox_y} {viewbox_w} {viewbox_h}"
    # 替换 viewBox（只改第一个 <svg 标签上的）
    local_svg, n = _VIEWBOX_RE.subn(r"\g<1>" + new_vb + r"\3", full_svg_data, count=1)
    if n == 0:
        print(f"导出失败 {output_path}: 未找到 viewBox 属性")
        return False

    # 去掉 width/height 上的 mm 单位（resvg 需要无单位像素值）
    clean_svg = _UNIT_RE.sub(r'\1="\2"', local_svg)

    try:
        png_bytes = resvg_py.svg_to_bytes(
            svg_string=clean_svg, width=output_px, height=output_px
        )
        with open(output_path, "wb") as f:
            f.write(bytes(png_bytes))
        return True
    except Exception as e:
        print(f"导出失败 {output_path}: {e}")
        return False


def export_digit_pngs(
    dwg: svgwrite.Drawing,
    digits: list[DigitInfo],
    export_cfg: ExportConfig,
    output_dir: str = "output",
) -> None:
    full_svg = dwg.tostring()
    for info in digits:
        digit_dir = os.path.join(output_dir, info.font_folder_name, str(info.digit))
        os.makedirs(digit_dir, exist_ok=True)
        png_path = os.path.join(
            digit_dir, f"{int(info.center_x)}_{int(info.center_y)}.png"
        )

        crop_size = info.size / 2
        half_crop = crop_size / 2
        ok = crop_svg_to_png(
            full_svg,
            info.center_x - half_crop,
            info.center_y - half_crop,
            crop_size,
            crop_size,
            png_path,
            export_cfg.png_size,
        )
        if ok:
            print(
                f"已保存数字 {info.digit} (字体: {info.font_folder_name}) -> {png_path}"
            )


def export_noise_pngs(
    dwg: svgwrite.Drawing,
    squares: list[Square],
    page_cfg: PageConfig,
    export_cfg: ExportConfig,
    noise_cfg: NoiseConfig,
    noise_font_folder: str = "Times_New_Roman",
) -> None:
    full_svg = dwg.tostring()
    noise_dir = os.path.join("output", f"noise_{noise_font_folder}")
    os.makedirs(noise_dir, exist_ok=True)

    half_crop = noise_cfg.crop_size_mm / 2
    min_cx = page_cfg.inner_x + half_crop
    max_cx = page_cfg.width_mm - page_cfg.margin - page_cfg.safe_margin - half_crop
    min_cy = page_cfg.inner_y + half_crop
    max_cy = page_cfg.height_mm - page_cfg.margin - page_cfg.safe_margin - half_crop

    if min_cx >= max_cx or min_cy >= max_cy:
        print("裁剪区域过大，无法生成噪声图像。")
        return

    noise_exported = 0
    max_attempts = noise_cfg.count * noise_cfg.max_attempts_factor
    attempts = 0

    while noise_exported < noise_cfg.count and attempts < max_attempts:
        attempts += 1
        cx = random.uniform(min_cx, max_cx)
        cy = random.uniform(min_cy, max_cy)
        crop_rect = (
            cx - half_crop,
            cy - half_crop,
            noise_cfg.crop_size_mm,
            noise_cfg.crop_size_mm,
        )
        crop_area = noise_cfg.crop_size_mm**2

        total_overlap = 0.0
        for sq in squares:
            bx, by, bw, bh = sq.bounding_rect()
            total_overlap += rectangle_overlap_area(crop_rect, (bx, by, bw, bh))
            if total_overlap / crop_area > noise_cfg.overlap_threshold:
                break

        ratio = total_overlap / crop_area
        if ratio > noise_cfg.overlap_threshold:
            continue

        png_path = os.path.join(
            noise_dir,
            f"noise_{int(cx)}_{int(cy)}_overlap{int(ratio * 100)}.png",
        )
        ok = crop_svg_to_png(
            full_svg,
            cx - half_crop,
            cy - half_crop,
            noise_cfg.crop_size_mm,
            noise_cfg.crop_size_mm,
            png_path,
            export_cfg.png_size,
        )
        if ok:
            print(f"已保存噪声图像 (重叠 {ratio * 100:.1f}%) -> {png_path}")
            noise_exported += 1

    if noise_exported < noise_cfg.count:
        print(
            f"噪声图像生成不足 ({noise_exported}/{noise_cfg.count})，已达最大尝试次数。"
        )


def save_svg_and_pdf(
    dwg: svgwrite.Drawing, filename: str, output_dir: str = "output"
) -> None:
    os.makedirs(os.path.join(output_dir, "svg"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "pdf"), exist_ok=True)

    svg_path = os.path.join(output_dir, "svg", filename)
    pdf_path = os.path.join(output_dir, "pdf", filename.replace(".svg", ".pdf"))

    dwg.saveas(svg_path)
    print(f"SVG -> {svg_path}")

    try:
        drawing = svg2rlg(svg_path)
        if drawing is not None:
            renderPDF.drawToFile(drawing, pdf_path)
            print(f"PDF -> {pdf_path}")
        else:
            print(f"PDF 导出失败: svg2rlg 返回 None ({svg_path})")
    except Exception as e:
        print(f"PDF 导出失败: {e}")
