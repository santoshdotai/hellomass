"""Pure geometry helpers used by the zone engine. Kept dependency-free and
side-effect-free so they're trivial to unit test."""
from __future__ import annotations

from typing import Sequence

Point = tuple[float, float]


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting point-in-polygon test. `polygon` is a list of (x, y) vertices."""
    x, y = point
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        if y > min(y1, y2):
            if y <= max(y1, y2):
                if x <= max(x1, x2):
                    if y1 != y2:
                        x_intersect = (y - y1) * (x2 - x1) / (y2 - y1) + x1
                    else:
                        x_intersect = x1
                    if x1 == x2 or x <= x_intersect:
                        inside = not inside
        x1, y1 = x2, y2
    return inside


def centroid_of_box(box: tuple[float, float, float, float]) -> Point:
    """box = (x1, y1, x2, y2) -> center point. Uses bottom-center for a
    more accurate 'floor position' of a standing person, falling back to
    the geometric center for non-person objects."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, y2)


def box_center(box: tuple[float, float, float, float]) -> Point:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def euclidean_distance(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _sign(p1: Point, p2: Point, p3: Point) -> float:
    return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Whether segment p1-p2 crosses segment p3-p4."""
    d1 = _sign(p1, p2, p3)
    d2 = _sign(p1, p2, p4)
    d3 = _sign(p3, p4, p1)
    d4 = _sign(p3, p4, p2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def which_side(line_a: Point, line_b: Point, point: Point) -> int:
    """Returns -1, 0, or 1 depending on which side of the line `point` is on."""
    value = _sign(line_a, line_b, point)
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def line_crossing_direction(line_a: Point, line_b: Point, prev_point: Point, curr_point: Point) -> str | None:
    """Detects whether the movement from prev_point -> curr_point crosses the
    line (line_a, line_b), and on which side each point falls, to classify
    the crossing as 'enter' or 'exit'. Returns None if no crossing happened.

    Direction convention: standing at line_a looking toward line_b, crossing
    from your right-hand side to your left-hand side is 'enter'. In practice
    this means the zone builder's entrance line direction is determined by
    the order the two points were clicked — draw it with that in mind (the
    UI can offer a "flip direction" control without changing this function)."""
    if not segments_intersect(prev_point, curr_point, line_a, line_b):
        return None
    prev_side = which_side(line_a, line_b, prev_point)
    curr_side = which_side(line_a, line_b, curr_point)
    if prev_side == curr_side or prev_side == 0 or curr_side == 0:
        return None
    # Convention: crossing from side -1 -> +1 is ENTER, +1 -> -1 is EXIT.
    return "enter" if prev_side < 0 < curr_side else "exit"


def polygon_area_normalized(polygon: Sequence[Point]) -> float:
    """Shoelace formula area for a normalized (0..1) polygon."""
    n = len(polygon)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
