from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


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
    squares: list[Square],
    exclude_index: int,
) -> bool:
    p1, p2 = edge
    for i, square in enumerate(squares):
        if i == exclude_index:
            continue
        for other_edge in square.get_edges():
            if line_intersect(p1, p2, other_edge[0], other_edge[1]):
                return True
    return False


def is_square_detectable(square: Square, all_squares: list[Square], index: int) -> bool:
    """判断正方形是否可检测：至少 2 条边 + 1 个角可见。

    边可见 = 不与其它正方形边相交 AND 边中点不在其它正方形内部。
    中点检测修复了"边完全隐藏在另一个正方形内部但无边相交"的误判。
    """
    edges = square.get_edges()
    corners = square.get_corners()
    visible_edges = 0
    visible_corners = 0

    for edge in edges:
        # 边与其它正方形边相交 → 不可见
        if edge_intersect_with_squares(edge, all_squares, index):
            continue

        # 边中点在其它正方形内部 → 整条边被吞没，不可见
        p1, p2 = edge
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        mid_covered = False
        for i, other in enumerate(all_squares):
            if i == index:
                continue
            if point_in_square(mid_x, mid_y, other):
                mid_covered = True
                break

        if not mid_covered:
            visible_edges += 1

    for corner in corners:
        px, py = corner
        covered = False
        for i, other_square in enumerate(all_squares):
            if i == index:
                continue
            if point_in_square(px, py, other_square):
                covered = True
                break
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

    使用外接圆近似：对角线的一半作为半径。
    """
    center_x = x + size / 2
    center_y = y + size / 2
    radius = size * math.sqrt(2) / 2
    min_x = margin + safe_margin
    max_x = page_width - margin - safe_margin
    min_y = margin + safe_margin
    max_y = page_height - margin - safe_margin
    return (
        center_x - radius >= min_x
        and center_x + radius <= max_x
        and center_y - radius >= min_y
        and center_y + radius <= max_y
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
