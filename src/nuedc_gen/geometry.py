from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


GEOMETRY_EPS = 1e-6


class ShapeType(Enum):
    """基本目标物图形类型"""

    SQUARE = "square"
    CIRCLE = "circle"
    TRIANGLE = "triangle"


@dataclass(frozen=True)
class Square:
    x: float
    y: float
    size: float
    angle: float

    @property
    def center_x(self) -> float:
        return self.x + self.size / 2

    @property
    def center_y(self) -> float:
        return self.y + self.size / 2

    @property
    def center(self) -> tuple[float, float]:
        return (self.center_x, self.center_y)

    def get_corners(self) -> list[tuple[float, float]]:
        half = self.size / 2
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
        angle_rad = math.radians(self.angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        rotated_corners = []
        for corner in corners:
            x_rot = corner[0] * cos_a - corner[1] * sin_a
            y_rot = corner[0] * sin_a + corner[1] * cos_a
            rotated_corners.append((self.center_x + x_rot, self.center_y + y_rot))
        return rotated_corners

    def get_edges(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        corners = self.get_corners()
        edges = []
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            edges.append((start, end))
        return edges

    def bounding_rect(self) -> tuple[float, float, float, float]:
        corners = self.get_corners()
        xs, ys = zip(*corners)
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def line_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return False
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    return (0 <= t <= 1) and (0 <= u <= 1)


def point_in_square(px: float, py: float, square: Square) -> bool:
    corners = square.get_corners()
    inside = False
    j = len(corners) - 1
    for i in range(len(corners)):
        xi, yi = corners[i]
        xj, yj = corners[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def edge_intersect_with_squares(
    edge: tuple[tuple[float, float], tuple[float, float]],
    other_squares: list[Square],
) -> bool:
    """检查边是否与其他正方形的边相交。

    Args:
        edge: 被检查的边
        other_squares: 其他正方形列表（不包含被检查边所属的正方形）
    """
    p1, p2 = edge
    for square in other_squares:
        for other_edge in square.get_edges():
            if line_intersect(p1, p2, other_edge[0], other_edge[1]):
                return True
    return False


def is_square_detectable(square: Square, other_squares: list[Square]) -> bool:
    """判断正方形是否可检测：至少 2 条边 + 1 个角可见。

    边可见 = 不与其它正方形边相交 AND 边中点不在其它正方形内部。
    中点检测修复了"边完全隐藏在另一个正方形内部但无边相交"的误判。

    Args:
        square: 被检查的正方形
        other_squares: 其他正方形列表（不包含 square 本身）
    """
    edges = square.get_edges()
    corners = square.get_corners()
    visible_edges = 0
    visible_corners = 0

    for edge in edges:
        # 边与其它正方形边相交 → 不可见
        if edge_intersect_with_squares(edge, other_squares):
            continue

        # 边中点在其它正方形内部 → 整条边被吞没，不可见
        p1, p2 = edge
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        mid_covered = any(
            point_in_square(mid_x, mid_y, other) for other in other_squares
        )

        if not mid_covered:
            visible_edges += 1

    for corner in corners:
        px, py = corner
        covered = any(
            point_in_square(px, py, other) for other in other_squares
        )
        if not covered:
            visible_corners += 1

    return visible_edges >= 2 and visible_corners >= 1


def is_square_in_bounds(
    x: float,
    y: float,
    size: float,
    angle: float,
    page_width: float,
    page_height: float,
    margin: float,
    safe_margin: float,
) -> bool:
    """判断正方形（含旋转）是否完全在页面安全区域内。

    直接检查旋转后的四个角点，避免外接圆近似过度收缩可用区域。
    """
    min_x = margin + safe_margin
    max_x = page_width - margin - safe_margin
    min_y = margin + safe_margin
    max_y = page_height - margin - safe_margin
    return all(
        min_x <= corner_x <= max_x and min_y <= corner_y <= max_y
        for corner_x, corner_y in Square(x, y, size, angle).get_corners()
    )


def rectangle_overlap_area(
    rect1: tuple[float, float, float, float],
    rect2: tuple[float, float, float, float],
) -> float:
    x1, y1, w1, h1 = rect1
    x2, y2, w2, h2 = rect2
    overlap_x1 = max(x1, x2)
    overlap_y1 = max(y1, y2)
    overlap_x2 = min(x1 + w1, x2 + w2)
    overlap_y2 = min(y1 + h1, y2 + h2)
    if overlap_x1 >= overlap_x2 or overlap_y1 >= overlap_y2:
        return 0.0
    return (overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1)


# ===== SAT碰撞检测 =====


def _project_polygon(corners: list[tuple[float, float]], axis: tuple[float, float]) -> tuple[float, float]:
    """将多边形投影到轴上，返回(min, max)"""
    projections = [x * axis[0] + y * axis[1] for x, y in corners]
    return min(projections), max(projections)


def _get_axes(corners: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """获取多边形的所有边法线作为分离轴"""
    axes = []
    n = len(corners)
    for i in range(n):
        edge = (corners[(i + 1) % n][0] - corners[i][0],
                corners[(i + 1) % n][1] - corners[i][1])
        # 法线（垂直向量）
        normal = (-edge[1], edge[0])
        # 归一化
        length = math.sqrt(normal[0] ** 2 + normal[1] ** 2)
        if length > 1e-10:
            axes.append((normal[0] / length, normal[1] / length))
    return axes


def sat_overlap(sq1: Square, sq2: Square) -> bool:
    """使用分离轴定理检测两个旋转正方形是否重叠"""
    corners1 = sq1.get_corners()
    corners2 = sq2.get_corners()

    # 获取两个多边形的所有分离轴
    axes = _get_axes(corners1) + _get_axes(corners2)

    for axis in axes:
        min1, max1 = _project_polygon(corners1, axis)
        min2, max2 = _project_polygon(corners2, axis)

        # 如果有间隙，则不重叠
        if max1 <= min2 + GEOMETRY_EPS or max2 <= min1 + GEOMETRY_EPS:
            return False

    return True  # 所有轴上都有重叠


def _line_intersection(p1: tuple[float, float], p2: tuple[float, float],
                       p3: tuple[float, float], p4: tuple[float, float]) -> tuple[float, float] | None:
    """计算两条线段的交点"""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    if 0 <= t <= 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (ix, iy)
    return None


def _is_point_inside_edge(point: tuple[float, float],
                          edge_start: tuple[float, float],
                          edge_end: tuple[float, float]) -> bool:
    """判断点是否在边的内侧（用于Sutherland-Hodgman裁剪）"""
    px, py = point
    ex, ey = edge_start
    dx, dy = edge_end
    return (dx - ex) * (py - ey) - (dy - ey) * (px - ex) >= 0


def polygon_intersection_area(poly1: list[tuple[float, float]],
                               poly2: list[tuple[float, float]]) -> float:
    """计算两个凸多边形的交集面积（Sutherland-Hodgman算法）"""
    if len(poly1) < 3 or len(poly2) < 3:
        return 0.0

    # 使用poly1的边裁剪poly2
    output = list(poly2)

    for i in range(len(poly1)):
        if len(output) == 0:
            return 0.0

        input_vertices = list(output)
        output = []

        edge_start = poly1[i]
        edge_end = poly1[(i + 1) % len(poly1)]

        for j in range(len(input_vertices)):
            current = input_vertices[j]
            previous = input_vertices[(j - 1) % len(input_vertices)]

            curr_inside = _is_point_inside_edge(current, edge_start, edge_end)
            prev_inside = _is_point_inside_edge(previous, edge_start, edge_end)

            if curr_inside:
                if not prev_inside:
                    intersection = _line_intersection(previous, current, edge_start, edge_end)
                    if intersection:
                        output.append(intersection)
                output.append(current)
            elif prev_inside:
                intersection = _line_intersection(previous, current, edge_start, edge_end)
                if intersection:
                    output.append(intersection)

    # 计算多边形面积（Shoelace公式）
    if len(output) < 3:
        return 0.0

    area = 0.0
    n = len(output)
    for i in range(n):
        j = (i + 1) % n
        area += output[i][0] * output[j][1]
        area -= output[j][0] * output[i][1]
    return abs(area) / 2.0


def square_overlap_area(sq1: Square, sq2: Square) -> float:
    """计算两个旋转正方形的实际重叠面积"""
    corners1 = sq1.get_corners()
    corners2 = sq2.get_corners()
    return polygon_intersection_area(corners1, corners2)


def square_overlap_ratio(sq1: Square, sq2: Square) -> float:
    """重叠面积占较小正方形面积的比例"""
    overlap = square_overlap_area(sq1, sq2)
    min_area = min(sq1.size * sq1.size, sq2.size * sq2.size)
    if min_area < 1e-10:
        return 0.0
    return overlap / min_area
