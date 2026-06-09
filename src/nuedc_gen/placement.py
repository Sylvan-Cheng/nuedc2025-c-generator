from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import (
    CExamTypeConfig,
    DigitConfig,
    Difficulty,
    ExtendedTargetConfig,
    FontConfig,
    PageConfig,
    SquareConfig,
)
from .digit import DigitInfo, assign_digit
from .geometry import Square, is_square_detectable, is_square_in_bounds


@dataclass(frozen=True)
class PlacementResult:
    squares: list[Square]
    digits: list[DigitInfo]


# ===== 共享原语 =====


def _random_position(page_cfg: PageConfig, size: float) -> tuple[float, float]:
    x = random.uniform(
        page_cfg.inner_x,
        page_cfg.width_mm - page_cfg.margin - page_cfg.safe_margin - size,
    )
    y = random.uniform(
        page_cfg.inner_y,
        page_cfg.height_mm - page_cfg.margin - page_cfg.safe_margin - size,
    )
    return x, y


def _random_size(square_cfg: SquareConfig) -> float:
    """生成随机正方形边长（5mm 为步进）"""
    min_steps = max(1, square_cfg.min_size_mm // 5)
    max_steps = max(1, square_cfg.max_size_mm // 5)
    return random.randint(min_steps, max_steps) * 5


def _is_overlapping(sq1: Square, sq2: Square, gap_mm: float = 0) -> bool:
    """判断两个正方形的边界矩形是否重叠（可扩展间距）"""
    r1 = sq1.bounding_rect()
    r2 = sq2.bounding_rect()
    x1, y1, w1, h1 = (
        r1[0] - gap_mm,
        r1[1] - gap_mm,
        r1[2] + 2 * gap_mm,
        r1[3] + 2 * gap_mm,
    )
    x2, y2, w2, h2 = r2
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)


def _overlap_area(sq1: Square, sq2: Square) -> float:
    """计算两个正方形边界矩形的重叠面积"""
    r1 = sq1.bounding_rect()
    r2 = sq2.bounding_rect()
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    return overlap_x * overlap_y


def _overlap_ratio(sq1: Square, sq2: Square) -> float:
    """重叠面积占较小正方形面积的比例"""
    min_area = min(sq1.size * sq1.size, sq2.size * sq2.size)
    if min_area == 0:
        return 0.0
    return _overlap_area(sq1, sq2) / min_area


def _count_overlaps(squares: list[Square]) -> int:
    """计算重叠的正方形对数"""
    overlaps = 0
    for i in range(len(squares)):
        for j in range(i + 1, len(squares)):
            if _is_overlapping(squares[i], squares[j]):
                overlaps += 1
    return overlaps


def _generate_grid_positions(
    count: int,
    page_cfg: PageConfig,
    size: float,
) -> list[tuple[float, float]]:
    """生成平均分布的网格位置"""
    cols = math.ceil(math.sqrt(count * page_cfg.inner_width / page_cfg.inner_height))
    rows = math.ceil(count / cols)
    cell_w = page_cfg.inner_width / cols
    cell_h = page_cfg.inner_height / rows

    positions = []
    for i in range(count):
        row = i // cols
        col = i % cols
        x = page_cfg.inner_x + col * cell_w + random.uniform(0, max(0, cell_w - size))
        y = page_cfg.inner_y + row * cell_h + random.uniform(0, max(0, cell_h - size))
        positions.append((x, y))
    return positions


def _assign_digits(
    squares: list[Square],
    font_cfg: FontConfig,
    overlap_threshold_mm: float,
) -> list[DigitInfo]:
    """为已放置的正方形批量分配数字"""
    digits: list[DigitInfo] = []
    digit_centers: list[tuple[float, float]] = []
    used_digits: set[int] = set()

    for sq in squares:
        cx, cy = sq.center
        digit_info = assign_digit(
            cx,
            cy,
            sq.size,
            sq.angle,
            used_digits,
            digit_centers,
            font_cfg,
            overlap_threshold_mm,
        )
        if digit_info:
            digits.append(digit_info)
            digit_centers.append((cx, cy))
            used_digits.add(digit_info.digit)
    return digits


def _is_gap_too_narrow(sq: Square, existing: Square, gap_mm: float) -> bool:
    """检查两个不重叠的正方形间距是否不足（返回 True 表示应拒绝）。

    使用 `and` 条件：当两个轴向间距都小于 gap_mm 时才拒绝。
    这对轴对齐情况（dx=0 时最小距离=dy）是正确的。
    对斜对角情况略偏保守（可能拒绝 sqrt(dx²+dy²) >= gap_mm 的布局）。
    """
    r1 = sq.bounding_rect()
    r2 = existing.bounding_rect()
    dx = max(0, max(r1[0], r2[0]) - min(r1[0] + r1[2], r2[0] + r2[2]))
    dy = max(0, max(r1[1], r2[1]) - min(r1[1] + r1[3], r2[1] + r2[3]))
    return dx < gap_mm and dy < gap_mm


# ===== 放置策略 =====


def _place_easy(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度0：1-3个正方形，不旋转，不重叠，平均分布"""
    count = random.randint(min_count, max_count)

    for _ in range(100):
        size = _random_size(square_cfg)
        if size > page_cfg.inner_width or size > page_cfg.inner_height:
            continue

        positions = _generate_grid_positions(count, page_cfg, size)
        placed: list[Square] = []
        valid = True

        for x, y in positions:
            sq = Square(x, y, size, 0)
            if not is_square_in_bounds(
                x,
                y,
                size,
                0,
                page_cfg.width_mm,
                page_cfg.height_mm,
                page_cfg.margin,
                page_cfg.safe_margin,
            ):
                valid = False
                break
            for existing in placed:
                if _is_overlapping(sq, existing, square_cfg.gap_mm):
                    valid = False
                    break
            if not valid:
                break
            placed.append(sq)

        if valid and len(placed) == count:
            digits = (
                _assign_digits(placed, font_cfg, digit_cfg.overlap_threshold_mm)
                if generate_digits
                else []
            )
            return PlacementResult(squares=placed, digits=digits)

    # 降级：保证尺寸 ≥ min_size_mm，必要时减少数量
    fallback_size = square_cfg.min_size_mm
    max_cols = max(1, int(page_cfg.inner_width / fallback_size))
    max_rows = max(1, int(page_cfg.inner_height / fallback_size))
    fallback_count = min(count, max_cols * max_rows)
    positions = _generate_grid_positions(fallback_count, page_cfg, fallback_size)
    placed = [Square(x, y, fallback_size, 0) for x, y in positions]
    digits = (
        _assign_digits(placed, font_cfg, digit_cfg.overlap_threshold_mm)
        if generate_digits
        else []
    )
    return PlacementResult(squares=placed, digits=digits)


def _place_medium(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度1：2-4个正方形，不旋转，最多1对重叠，重叠面积不超过30%，其余留间距"""
    count = random.randint(min_count, max_count)
    max_overlap_ratio = 0.3

    for _ in range(500):
        placed: list[Square] = []
        sizes = [_random_size(square_cfg) for _ in range(count)]

        for i, size in enumerate(sizes):
            placed_one = False
            for _ in range(100):
                x, y = _random_position(page_cfg, size)
                sq = Square(x, y, size, 0)

                if not is_square_in_bounds(
                    x,
                    y,
                    size,
                    0,
                    page_cfg.width_mm,
                    page_cfg.height_mm,
                    page_cfg.margin,
                    page_cfg.safe_margin,
                ):
                    continue

                existing_overlaps = _count_overlaps(placed)
                valid = True
                new_overlap_count = 0

                for existing in placed:
                    if _is_overlapping(sq, existing):
                        ratio = _overlap_ratio(sq, existing)
                        if ratio > max_overlap_ratio:
                            valid = False
                            break
                        new_overlap_count += 1
                    else:
                        if _is_gap_too_narrow(sq, existing, square_cfg.gap_mm):
                            valid = False
                            break

                total_overlaps = existing_overlaps + new_overlap_count
                if valid and total_overlaps <= 1:
                    placed.append(sq)
                    placed_one = True
                    break

            if not placed_one:
                break

        if len(placed) == count:
            digits = (
                _assign_digits(placed, font_cfg, digit_cfg.overlap_threshold_mm)
                if generate_digits
                else []
            )
            return PlacementResult(squares=placed, digits=digits)

    # 降级
    return _place_easy(
        page_cfg,
        square_cfg,
        max(2, min_count),
        max_count,
        font_cfg,
        digit_cfg,
        generate_digits,
    )


def _try_place_hard(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
    relaxed: bool = False,
) -> PlacementResult:
    """困难模式核心循环。relaxed=True 时跳过可检测性检查并增加尝试次数。"""
    max_attempts = count * (400 if relaxed else 200)

    placed: list[Square] = []
    digits: list[DigitInfo] = []
    digit_centers: list[tuple[float, float]] = []
    used_digits: set[int] = set()

    attempts = 0
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        size = _random_size(square_cfg)

        if size > page_cfg.inner_width or size > page_cfg.inner_height:
            continue

        x, y = _random_position(page_cfg, size)
        angle = random.uniform(0, 360)

        if not is_square_in_bounds(
            x,
            y,
            size,
            angle,
            page_cfg.width_mm,
            page_cfg.height_mm,
            page_cfg.margin,
            page_cfg.safe_margin,
        ):
            continue

        new_square = Square(x, y, size, angle)
        temp_squares = placed + [new_square]
        new_index = len(placed)

        # relaxed 模式跳过可检测性检查
        if not relaxed and not is_square_detectable(
            new_square, temp_squares, new_index
        ):
            continue

        digit_info = None
        if generate_digits:
            center_x = x + size / 2
            center_y = y + size / 2
            digit_info = assign_digit(
                center_x,
                center_y,
                size,
                angle,
                used_digits,
                digit_centers,
                font_cfg,
                digit_cfg.overlap_threshold_mm,
            )
            if digit_info is None:
                continue
            digit_centers.append((center_x, center_y))
            used_digits.add(digit_info.digit)
            digits.append(digit_info)

        placed.append(new_square)

    return PlacementResult(squares=placed, digits=digits)


def _place_hard(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度2：3-5个正方形，随机旋转，可重叠。

    两层降级策略保证始终返回 ≥ min_count 个正方形：
    1. 严格约束（可检测 + 数字分配）
    2. 放宽约束（跳过可检测性，增加尝试次数）
    3. 最终降级到 _place_easy（无旋转无重叠）
    """
    count = random.randint(min_count, max_count)

    # 第一轮：严格约束
    result = _try_place_hard(
        page_cfg, square_cfg, count, font_cfg, digit_cfg, generate_digits, relaxed=False
    )
    if len(result.squares) >= min_count:
        return result

    # 第二轮：放宽约束
    result = _try_place_hard(
        page_cfg, square_cfg, count, font_cfg, digit_cfg, generate_digits, relaxed=True
    )
    if len(result.squares) >= min_count:
        return result

    # 最终降级：无旋转无重叠，保证数量
    return _place_easy(
        page_cfg, square_cfg, min_count, max_count, font_cfg, digit_cfg, generate_digits
    )


# ===== 公共接口 =====


def _dispatch_place(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    min_count: int,
    max_count: int,
    allow_overlap: bool,
    allow_rotation: bool,
    generate_digits: bool,
) -> PlacementResult:
    """统一的布局策略入口：根据参数选择策略"""
    if not allow_overlap and not allow_rotation:
        return _place_easy(
            page_cfg,
            square_cfg,
            min_count,
            max_count,
            font_cfg,
            digit_cfg,
            generate_digits,
        )
    elif allow_overlap and not allow_rotation:
        return _place_medium(
            page_cfg,
            square_cfg,
            min_count,
            max_count,
            font_cfg,
            digit_cfg,
            generate_digits,
        )
    else:
        return _place_hard(
            page_cfg,
            square_cfg,
            min_count,
            max_count,
            font_cfg,
            digit_cfg,
            generate_digits,
        )


def place_squares(
    page_cfg: PageConfig,
    ext_cfg: ExtendedTargetConfig,
    font_cfg: FontConfig,
    generate_digits: bool = True,
) -> PlacementResult:
    """根据难度级别放置正方形"""
    if ext_cfg.difficulty == Difficulty.EASY:
        allow_overlap, allow_rotation = False, False
    elif ext_cfg.difficulty == Difficulty.MEDIUM:
        allow_overlap, allow_rotation = True, False
    else:
        allow_overlap, allow_rotation = True, True

    return _dispatch_place(
        page_cfg,
        ext_cfg.square,
        font_cfg,
        ext_cfg.digit,
        ext_cfg.min_count,
        ext_cfg.max_count,
        allow_overlap,
        allow_rotation,
        generate_digits,
    )


def place_c_exam_page(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    digit_cfg: DigitConfig,
    font_cfg: FontConfig,
    type_cfg: CExamTypeConfig,
) -> PlacementResult:
    """根据 C 题类型配置生成一页布局"""
    return _dispatch_place(
        page_cfg,
        square_cfg,
        font_cfg,
        digit_cfg,
        type_cfg.effective_min,
        type_cfg.effective_max,
        type_cfg.allow_overlap,
        type_cfg.allow_rotation,
        type_cfg.generate_digits,
    )
