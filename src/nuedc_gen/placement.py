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
    OverlapConfig,
    PageConfig,
    SquareConfig,
)
from .digit import DigitInfo, assign_digit
from .geometry import (
    Square,
    is_square_detectable,
    is_square_in_bounds,
    sat_overlap,
    square_overlap_ratio,
)

# 最大重试次数
MAX_ATTEMPTS_EASY = 500
MAX_ATTEMPTS_MEDIUM = 300
MAX_ATTEMPTS_HARD = 500
MAX_PLACEMENT_TRIES = 500
OVERLAP_EPS = 1e-6


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
    min_steps = max(1, math.ceil(square_cfg.min_size_mm / 5))
    max_steps = max(1, math.floor(square_cfg.max_size_mm / 5))
    if min_steps > max_steps:
        raise ValueError("正方形尺寸配置无可用的5mm步进值")
    return random.randint(min_steps, max_steps) * 5


def _limited_square_config(
    square_cfg: SquareConfig,
    max_size_mm: int | None = None,
    gap_mm: float | None = None,
) -> SquareConfig:
    return SquareConfig(
        min_size_mm=square_cfg.min_size_mm,
        max_size_mm=min(square_cfg.max_size_mm, max_size_mm or square_cfg.max_size_mm),
        gap_mm=square_cfg.gap_mm if gap_mm is None else gap_mm,
        dense_gap_mm=square_cfg.dense_gap_mm,
    )


def _preferred_counts(min_count: int, max_count: int) -> list[int]:
    first = random.randint(min_count, max_count)
    rest = [count for count in range(min_count, max_count + 1) if count != first]
    random.shuffle(rest)
    return [first] + rest


def _count_overlaps(squares: list[Square]) -> int:
    """计算实际重叠面积大于0的正方形对数。"""
    overlaps = 0
    for i in range(len(squares)):
        for j in range(i + 1, len(squares)):
            if square_overlap_ratio(squares[i], squares[j]) > OVERLAP_EPS:
                overlaps += 1
    return overlaps


def _has_overlap(sq: Square, squares: list[Square]) -> bool:
    """检查正方形是否与列表中任意正方形重叠"""
    for other in squares:
        if square_overlap_ratio(sq, other) > OVERLAP_EPS:
            return True
    return False


def _overlap_ratio_valid(ratio: float, min_ratio: float, max_ratio: float) -> bool:
    return ratio <= OVERLAP_EPS or min_ratio <= ratio <= max_ratio


def _overlap_count_within_limits(
    squares: list[Square],
    min_ratio: float,
    max_ratio: float,
) -> int | None:
    overlap_count = 0
    for i in range(len(squares)):
        for j in range(i + 1, len(squares)):
            ratio = square_overlap_ratio(squares[i], squares[j])
            if not _overlap_ratio_valid(ratio, min_ratio, max_ratio):
                return None
            if ratio > OVERLAP_EPS:
                overlap_count += 1
    return overlap_count


def _non_overlapping_gaps_valid(squares: list[Square], gap_mm: float) -> bool:
    for i in range(len(squares)):
        for j in range(i + 1, len(squares)):
            if square_overlap_ratio(squares[i], squares[j]) > OVERLAP_EPS:
                return False
            if _is_gap_too_narrow(squares[i], squares[j], gap_mm):
                return False
    return True


def _max_overlap_ratio(sq: Square, squares: list[Square]) -> float:
    """计算正方形与列表中所有正方形的最大重叠率（精确计算）"""
    max_ratio = 0.0
    for other in squares:
        ratio = square_overlap_ratio(sq, other)
        max_ratio = max(max_ratio, ratio)
    return max_ratio


def _is_gap_too_narrow(sq: Square, existing: Square, gap_mm: float) -> bool:
    """检查两个不重叠的正方形间距是否不足"""
    r1 = sq.bounding_rect()
    r2 = existing.bounding_rect()
    dx = max(0, max(r1[0], r2[0]) - min(r1[0] + r1[2], r2[0] + r2[2]))
    dy = max(0, max(r1[1], r2[1]) - min(r1[1] + r1[3], r2[1] + r2[3]))
    return dx < gap_mm and dy < gap_mm


def _assign_digits(
    squares: list[Square],
    font_cfg: FontConfig,
    overlap_threshold_mm: float,
) -> list[DigitInfo]:
    """为已放置的正方形批量分配数字"""
    digits: list[DigitInfo] = []
    digit_centers: list[tuple[float, float]] = []
    used_digits: set[int] = set()

    for i, sq in enumerate(squares):
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


def _build_result(
    squares: list[Square],
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult | None:
    digits = (
        _assign_digits(squares, font_cfg, digit_cfg.overlap_threshold_mm)
        if generate_digits
        else []
    )
    if generate_digits and len(digits) != len(squares):
        return None
    return PlacementResult(squares=squares, digits=digits)


# ===== 均匀分布辅助函数 =====


def _biased_position(
    page_cfg: PageConfig,
    size: float,
    placed: list[Square],
    grid_divisions: int = 3,
    bias_strength: float = 0.6,
) -> tuple[float, float]:
    """带网格偏好的位置生成，使正方形相对均匀分布。

    将页面划分为 grid_divisions x grid_divisions 网格，
    以更高概率从稀疏网格中采样。

    Args:
        page_cfg: 页面配置
        size: 正方形边长
        placed: 已放置的正方形列表
        grid_divisions: 网格划分数
        bias_strength: 偏好强度，0=纯随机，1=完全均匀
    """
    inner_x = page_cfg.inner_x
    inner_y = page_cfg.inner_y
    inner_w = page_cfg.width_mm - 2 * page_cfg.margin - 2 * page_cfg.safe_margin
    inner_h = page_cfg.height_mm - 2 * page_cfg.margin - 2 * page_cfg.safe_margin

    cell_w = inner_w / grid_divisions
    cell_h = inner_h / grid_divisions

    # 统计每个网格中的正方形数量
    grid_count = [[0] * grid_divisions for _ in range(grid_divisions)]
    for sq in placed:
        cx, cy = sq.center
        col = min(int((cx - inner_x) / cell_w), grid_divisions - 1)
        row = min(int((cy - inner_y) / cell_h), grid_divisions - 1)
        if 0 <= col < grid_divisions and 0 <= row < grid_divisions:
            grid_count[row][col] += 1

    # 计算每个网格的权重（数量越少权重越高）
    weights = []
    grid_cells = []
    for row in range(grid_divisions):
        for col in range(grid_divisions):
            grid_cells.append((row, col))
            # 权重 = 1 / (数量 + 1)，稀疏网格权重更高
            weight = 1.0 / (grid_count[row][col] + 1)
            weights.append(weight)

    # 根据 bias_strength 决定是否使用偏好
    if random.random() < bias_strength and placed:
        # 使用网格偏好
        chosen_cell = random.choices(grid_cells, weights=weights, k=1)[0]
        row, col = chosen_cell
        # 在选中网格内采样中心点，再换算成左上角；正方形大于网格时自动裁剪到可行范围。
        center_min_x = inner_x + size / 2
        center_max_x = inner_x + inner_w - size / 2
        center_min_y = inner_y + size / 2
        center_max_y = inner_y + inner_h - size / 2
        cell_min_x = inner_x + col * cell_w
        cell_max_x = inner_x + (col + 1) * cell_w
        cell_min_y = inner_y + row * cell_h
        cell_max_y = inner_y + (row + 1) * cell_h
        min_cx = max(center_min_x, cell_min_x)
        max_cx = min(center_max_x, cell_max_x)
        min_cy = max(center_min_y, cell_min_y)
        max_cy = min(center_max_y, cell_max_y)
        if min_cx <= max_cx and min_cy <= max_cy:
            x = random.uniform(min_cx, max_cx) - size / 2
            y = random.uniform(min_cy, max_cy) - size / 2
        else:
            x, y = _random_position(page_cfg, size)
    else:
        # 纯随机
        x, y = _random_position(page_cfg, size)

    # 确保在边界内
    x = max(inner_x, min(x, page_cfg.width_mm - page_cfg.margin - page_cfg.safe_margin - size))
    y = max(inner_y, min(y, page_cfg.height_mm - page_cfg.margin - page_cfg.safe_margin - size))

    return x, y


# ===== 放置原语 =====


def _place_square_no_overlap(
    placed: list[Square],
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    use_grid_bias: bool = True,
) -> Square | None:
    """放置一个正方形，确保与已放置的正方形不重叠，支持网格偏好。"""
    for _ in range(MAX_PLACEMENT_TRIES):
        size = _random_size(square_cfg)

        if use_grid_bias and placed:
            x, y = _biased_position(page_cfg, size, placed)
        else:
            x, y = _random_position(page_cfg, size)

        if not is_square_in_bounds(
            x, y, size, 0,
            page_cfg.width_mm, page_cfg.height_mm,
            page_cfg.margin, page_cfg.safe_margin,
        ):
            continue

        sq = Square(x, y, size, 0)

        # 检查是否与已放置的正方形重叠
        overlap = False
        for existing in placed:
            if sat_overlap(sq, existing):
                overlap = True
                break
            if _is_gap_too_narrow(sq, existing, square_cfg.gap_mm):
                overlap = True
                break

        if not overlap:
            return sq

    return None


def _place_square_with_overlap_precise(
    target: Square,
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_overlap_ratio: float,
    max_overlap_ratio: float,
) -> Square | None:
    """使用精确重叠率计算放置正方形，确保与目标正方形重叠。

    Args:
        target: 目标正方形
        page_cfg: 页面配置
        square_cfg: 正方形配置
        min_overlap_ratio: 最小重叠率
        max_overlap_ratio: 最大重叠率
    """
    cx1, cy1 = target.center

    for _ in range(MAX_PLACEMENT_TRIES):
        size2 = _random_size(square_cfg)

        # 在目标周围采样位置
        max_dist = (target.size + size2) / 2
        angle = random.uniform(0, 2 * math.pi)

        # 距离范围：从紧密重叠到略微分离
        # 使用较大的距离范围，然后通过精确验证筛选
        dist = random.uniform(max_dist * 0.5, max_dist * 1.3)

        cx2 = cx1 + dist * math.cos(angle)
        cy2 = cy1 + dist * math.sin(angle)

        # 转换为左上角坐标
        new_x = cx2 - size2 / 2
        new_y = cy2 - size2 / 2

        # 检查是否在页面内
        if not is_square_in_bounds(
            new_x, new_y, size2, 0,
            page_cfg.width_mm, page_cfg.height_mm,
            page_cfg.margin, page_cfg.safe_margin,
        ):
            continue

        new_sq = Square(new_x, new_y, size2, 0)

        # 精确验证重叠率
        ratio = square_overlap_ratio(target, new_sq)
        if min_overlap_ratio <= ratio <= max_overlap_ratio:
            return new_sq

    return None


def _place_square_with_overlap_rotated(
    target: Square,
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_overlap_ratio: float,
    max_overlap_ratio: float,
) -> Square | None:
    """放置旋转正方形，使用精确重叠率计算，确保与目标正方形重叠。"""
    cx1, cy1 = target.center

    for _ in range(MAX_PLACEMENT_TRIES):
        size2 = _random_size(square_cfg)
        new_angle = random.uniform(0, 360)

        # 在目标周围采样位置
        max_dist = (target.size + size2) / 2
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(max_dist * 0.3, max_dist * 1.2)

        cx2 = cx1 + dist * math.cos(angle)
        cy2 = cy1 + dist * math.sin(angle)

        # 转换为左上角坐标
        new_x = cx2 - size2 / 2
        new_y = cy2 - size2 / 2

        # 检查是否在页面内
        if not is_square_in_bounds(
            new_x, new_y, size2, new_angle,
            page_cfg.width_mm, page_cfg.height_mm,
            page_cfg.margin, page_cfg.safe_margin,
        ):
            continue

        new_sq = Square(new_x, new_y, size2, new_angle)

        # 检查可检测性
        if not is_square_detectable(new_sq, [target]):
            continue

        # 精确验证重叠率
        ratio = square_overlap_ratio(target, new_sq)
        if min_overlap_ratio <= ratio <= max_overlap_ratio:
            return new_sq

    return None


def _place_square_with_overlap_limit(
    placed: list[Square],
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    min_overlap_ratio: float,
    max_overlap_ratio: float,
) -> Square | None:
    """放置一个正方形，确保与所有已放置正方形的重叠率在配置范围内。

    允许不重叠（重叠率为0），也允许重叠但不超过 max_overlap_ratio。
    使用网格偏好确保均匀分布。
    """
    for _ in range(MAX_PLACEMENT_TRIES):
        size = _random_size(square_cfg)
        x, y = _biased_position(page_cfg, size, placed)

        if not is_square_in_bounds(
            x, y, size, 0,
            page_cfg.width_mm, page_cfg.height_mm,
            page_cfg.margin, page_cfg.safe_margin,
        ):
            continue

        sq = Square(x, y, size, 0)

        # 检查与所有已放置正方形的重叠率
        valid = True
        for existing in placed:
            ratio = square_overlap_ratio(sq, existing)
            if not _overlap_ratio_valid(ratio, min_overlap_ratio, max_overlap_ratio):
                valid = False
                break
            if ratio <= OVERLAP_EPS and _is_gap_too_narrow(
                sq, existing, square_cfg.gap_mm
            ):
                valid = False
                break

        if valid:
            return sq

    return None


# ===== 放置策略 =====


def _place_easy(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    overlap_cfg: OverlapConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度0：2-4个正方形，随机大小，不旋转，不重叠，相对均匀分布。"""
    attempts_per_count = MAX_ATTEMPTS_EASY // (max_count - min_count + 1)

    for count in _preferred_counts(min_count, max_count):
        for _ in range(attempts_per_count):
            placed: list[Square] = []

            for i in range(count):
                # 当需要放置更多正方形时，限制最大尺寸
                if count >= 3:
                    temp_cfg = _limited_square_config(
                        square_cfg,
                        max_size_mm=80,
                        gap_mm=min(square_cfg.gap_mm, square_cfg.dense_gap_mm),
                    )
                else:
                    temp_cfg = square_cfg

                sq = _place_square_no_overlap(
                    placed, page_cfg, temp_cfg, use_grid_bias=True
                )
                if sq is None:
                    break
                placed.append(sq)

            if len(placed) == count and _non_overlapping_gaps_valid(placed, temp_cfg.gap_mm):
                result = _build_result(placed, font_cfg, digit_cfg, generate_digits)
                if result is not None:
                    return result

    raise RuntimeError(
        f"难度0布局失败：无法在 {MAX_ATTEMPTS_EASY} 次尝试内生成满足条件的布局"
    )


def _place_medium(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    overlap_cfg: OverlapConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度1：3-4个正方形，不旋转，恰好1对重叠，相对均匀分布。

    重叠率从配置读取（默认 5%-20%）。
    限制：最多1对重叠。
    """
    min_overlap_ratio = overlap_cfg.min_ratio_medium
    max_overlap_ratio = overlap_cfg.max_ratio_medium
    attempts_per_count = MAX_ATTEMPTS_MEDIUM // (max_count - min_count + 1)

    for count in _preferred_counts(min_count, max_count):
        for _ in range(attempts_per_count):
            attempt_cfg = (
                _limited_square_config(square_cfg, max_size_mm=90)
                if count >= 4
                else square_cfg
            )
            placed: list[Square] = []

            # 1. 放置第一个正方形（网格偏好）
            first = _place_square_no_overlap(
                placed, page_cfg, attempt_cfg, use_grid_bias=True
            )
            if first is None:
                continue
            placed.append(first)

            # 2. 放置第二个正方形，必须与第一个重叠（精确重叠率）
            second = _place_square_with_overlap_precise(
                placed[0], page_cfg, attempt_cfg,
                min_overlap_ratio, max_overlap_ratio
            )
            if second is None:
                continue
            placed.append(second)

            # 3. 放置后续正方形，不允许再重叠
            for i in range(2, count):
                sq = _place_square_no_overlap(
                    placed, page_cfg, attempt_cfg, use_grid_bias=True
                )
                if sq is None:
                    break
                placed.append(sq)

            overlap_count = _overlap_count_within_limits(
                placed, min_overlap_ratio, max_overlap_ratio
            )
            if len(placed) == count and overlap_count == 1:
                result = _build_result(placed, font_cfg, digit_cfg, generate_digits)
                if result is not None:
                    return result

    raise RuntimeError(
        f"难度1布局失败：无法在 {MAX_ATTEMPTS_MEDIUM} 次尝试内生成满足条件的布局"
    )


def _place_hard(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    overlap_cfg: OverlapConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
) -> PlacementResult:
    """难度2：3-5个正方形，随机旋转，可重叠，相对均匀分布。

    重叠率从配置读取（默认 5%-40%）。
    所有正方形必须满足可检测性（≥2条边+1个角可见）。
    必须至少1对重叠。
    """
    min_overlap_ratio = overlap_cfg.min_ratio_hard
    max_overlap_ratio = overlap_cfg.max_ratio_hard
    attempts_per_count = MAX_ATTEMPTS_HARD // (max_count - min_count + 1)

    for count in _preferred_counts(min_count, max_count):
        for _ in range(attempts_per_count):
            if count >= 5:
                attempt_cfg = _limited_square_config(square_cfg, max_size_mm=80)
            elif count >= 4:
                attempt_cfg = _limited_square_config(square_cfg, max_size_mm=90)
            else:
                attempt_cfg = square_cfg
            placed: list[Square] = []

            # 1. 放置第一个正方形（随机旋转，网格偏好）
            for _ in range(MAX_PLACEMENT_TRIES):
                size = _random_size(attempt_cfg)
                x, y = (
                    _biased_position(page_cfg, size, placed)
                    if placed
                    else _random_position(page_cfg, size)
                )
                angle = random.uniform(0, 360)

                if not is_square_in_bounds(
                    x, y, size, angle,
                    page_cfg.width_mm, page_cfg.height_mm,
                    page_cfg.margin, page_cfg.safe_margin,
                ):
                    continue

                sq = Square(x, y, size, angle)
                placed.append(sq)
                break

            if not placed:
                continue

            # 2. 放置第二个正方形，必须与第一个重叠
            second = _place_square_with_overlap_rotated(
                placed[0], page_cfg, attempt_cfg,
                min_overlap_ratio, max_overlap_ratio
            )
            if second is None:
                continue
            placed.append(second)

            # 3. 放置后续正方形
            for i in range(2, count):
                placed_one = False
                for _ in range(MAX_PLACEMENT_TRIES):
                    size = _random_size(attempt_cfg)
                    x, y = _biased_position(page_cfg, size, placed)
                    angle = random.uniform(0, 360)

                    if not is_square_in_bounds(
                        x, y, size, angle,
                        page_cfg.width_mm, page_cfg.height_mm,
                        page_cfg.margin, page_cfg.safe_margin,
                    ):
                        continue

                    sq = Square(x, y, size, angle)

                    # 检查新正方形的可检测性
                    if not is_square_detectable(sq, placed):
                        continue

                    ratios_valid = True
                    for existing in placed:
                        ratio = square_overlap_ratio(sq, existing)
                        if not _overlap_ratio_valid(
                            ratio, min_overlap_ratio, max_overlap_ratio
                        ):
                            ratios_valid = False
                            break
                    if not ratios_valid:
                        continue

                    # 检查放置新正方形后，所有已放置正方形是否仍然可检测
                    all_still_detectable = True
                    for j, existing in enumerate(placed):
                        others = [placed[k] for k in range(len(placed)) if k != j] + [sq]
                        if not is_square_detectable(existing, others):
                            all_still_detectable = False
                            break

                    if not all_still_detectable:
                        continue

                    placed.append(sq)
                    placed_one = True
                    break

                if not placed_one:
                    break

            overlap_count = _overlap_count_within_limits(
                placed, min_overlap_ratio, max_overlap_ratio
            )
            if len(placed) == count and overlap_count is not None and overlap_count >= 1:
                if not all(
                    is_square_detectable(square, placed[:i] + placed[i + 1:])
                    for i, square in enumerate(placed)
                ):
                    continue
                result = _build_result(placed, font_cfg, digit_cfg, generate_digits)
                if result is not None:
                    return result

    raise RuntimeError(
        f"难度2布局失败：无法在 {MAX_ATTEMPTS_HARD} 次尝试内生成满足条件的布局"
    )


def _place_single(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
    allow_rotation: bool,
) -> PlacementResult:
    """C题标准模式：单个正方形，可选旋转。"""
    for _ in range(MAX_PLACEMENT_TRIES):
        size = _random_size(square_cfg)
        x, y = _random_position(page_cfg, size)
        angle = random.uniform(0, 360) if allow_rotation else 0
        if not is_square_in_bounds(
            x, y, size, angle,
            page_cfg.width_mm, page_cfg.height_mm,
            page_cfg.margin, page_cfg.safe_margin,
        ):
            continue
        squares = [Square(x, y, size, angle)]
        result = _build_result(squares, font_cfg, digit_cfg, generate_digits)
        if result is not None:
            return result
    raise RuntimeError("单正方形布局失败：无法生成满足边界条件的布局")


def _place_c_exam_multi(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    overlap_cfg: OverlapConfig,
    min_count: int,
    max_count: int,
    font_cfg: FontConfig,
    digit_cfg: DigitConfig,
    generate_digits: bool,
    allow_overlap: bool,
) -> PlacementResult:
    """C题标准模式：2-4个正方形，允许但不强制重叠。"""
    min_overlap_ratio = overlap_cfg.min_ratio_medium
    max_overlap_ratio = overlap_cfg.max_ratio_medium
    attempts_per_count = MAX_ATTEMPTS_MEDIUM // (max_count - min_count + 1)

    for count in _preferred_counts(min_count, max_count):
        attempt_cfg = (
            _limited_square_config(square_cfg, max_size_mm=90)
            if count >= 4
            else square_cfg
        )
        for _ in range(attempts_per_count):
            placed: list[Square] = []
            first = _place_square_no_overlap(
                placed, page_cfg, attempt_cfg, use_grid_bias=True
            )
            if first is None:
                continue
            placed.append(first)

            for i in range(1, count):
                sq = None
                can_add_overlap = allow_overlap and _count_overlaps(placed) == 0
                if can_add_overlap and random.random() < 0.45:
                    target = random.choice(placed)
                    sq = _place_square_with_overlap_precise(
                        target,
                        page_cfg,
                        attempt_cfg,
                        min_overlap_ratio,
                        max_overlap_ratio,
                    )
                    if sq is not None:
                        extra_overlap = False
                        for existing in placed:
                            if existing == target:
                                continue
                            if square_overlap_ratio(sq, existing) > OVERLAP_EPS:
                                extra_overlap = True
                                break
                            if _is_gap_too_narrow(sq, existing, attempt_cfg.gap_mm):
                                extra_overlap = True
                                break
                        if extra_overlap:
                            sq = None
                if sq is None:
                    sq = _place_square_no_overlap(
                        placed, page_cfg, attempt_cfg, use_grid_bias=True
                    )
                if sq is None:
                    break
                placed.append(sq)

            overlap_count = _overlap_count_within_limits(
                placed,
                min_overlap_ratio if allow_overlap else 0.0,
                max_overlap_ratio if allow_overlap else 0.0,
            )
            if (
                len(placed) == count
                and overlap_count is not None
                and overlap_count <= (1 if allow_overlap else 0)
            ):
                result = _build_result(placed, font_cfg, digit_cfg, generate_digits)
                if result is not None:
                    return result

    raise RuntimeError("C题多正方形布局失败：无法生成满足条件的布局")


# ===== 公共接口 =====


def _dispatch_place(
    page_cfg: PageConfig,
    square_cfg: SquareConfig,
    overlap_cfg: OverlapConfig,
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
            page_cfg, square_cfg, overlap_cfg,
            min_count, max_count,
            font_cfg, digit_cfg, generate_digits,
        )
    elif allow_overlap and not allow_rotation:
        return _place_medium(
            page_cfg, square_cfg, overlap_cfg,
            min_count, max_count,
            font_cfg, digit_cfg, generate_digits,
        )
    else:
        return _place_hard(
            page_cfg, square_cfg, overlap_cfg,
            min_count, max_count,
            font_cfg, digit_cfg, generate_digits,
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
        ext_cfg.overlap,
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
    overlap_cfg: OverlapConfig | None = None,
) -> PlacementResult:
    """根据 C 题类型配置生成一页布局"""
    if overlap_cfg is None:
        overlap_cfg = OverlapConfig()

    if type_cfg.effective_min == 1 and type_cfg.effective_max == 1:
        return _place_single(
            page_cfg,
            square_cfg,
            font_cfg,
            digit_cfg,
            type_cfg.generate_digits,
            type_cfg.allow_rotation,
        )

    if not type_cfg.allow_rotation:
        return _place_c_exam_multi(
            page_cfg,
            square_cfg,
            overlap_cfg,
            type_cfg.effective_min,
            type_cfg.effective_max,
            font_cfg,
            digit_cfg,
            type_cfg.generate_digits,
            type_cfg.allow_overlap,
        )

    raise ValueError("C题标准模式暂不支持多个旋转正方形组合")
