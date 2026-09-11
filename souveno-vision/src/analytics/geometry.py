"""Pure, dependency-free geometry on normalised (0..1) coordinates.

Everything spatial in Souveno works in normalised space so that a zone drawn on
a 640x360 substream still applies to the 1920x1080 main stream."""
from __future__ import annotations

from typing import Sequence

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # x1, y1, x2, y2


def clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else float(v)


def bottom_center(box: Box) -> Point:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, y2)


def box_center(box: Box) -> Point:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def normalize_point(point: Point, width: float, height: float) -> Point:
    return (point[0] / float(width), point[1] / float(height))


def denormalize_point(point: Point, width: float, height: float) -> tuple[int, int]:
    return (int(round(point[0] * width)), int(round(point[1] * height)))


def normalize_box(box: Box, width: float, height: float) -> Box:
    return (box[0] / width, box[1] / height, box[2] / width, box[3] / height)


def scale_box(box: Box, sx: float, sy: float) -> Box:
    return (box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy)


def distance(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting test. Points exactly on an edge count as inside (stable for hysteresis)."""
    x, y = point
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if _on_segment((x, y), (xi, yi), (xj, yj)):
            return True
        if (yi > y) != (yj > y):
            x_int = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_int:
                inside = not inside
        j = i
    return inside


def _on_segment(p: Point, a: Point, b: Point, eps: float = 1e-9) -> bool:
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > eps:
        return False
    return min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps and \
        min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps


def polygon_area(polygon: Sequence[Point]) -> float:
    n = len(polygon)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def polygon_centroid(polygon: Sequence[Point]) -> Point:
    n = len(polygon)
    if n == 0:
        return (0.0, 0.0)
    return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Proper or touching intersection of segments p1-p2 and q1-q2."""
    d1 = _orient(q1, q2, p1)
    d2 = _orient(q1, q2, p2)
    d3 = _orient(p1, p2, q1)
    d4 = _orient(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return True
    if d1 == 0 and _on_segment(p1, q1, q2):
        return True
    if d2 == 0 and _on_segment(p2, q1, q2):
        return True
    if d3 == 0 and _on_segment(q1, p1, p2):
        return True
    if d4 == 0 and _on_segment(q2, p1, p2):
        return True
    return False


def signed_distance_to_line(a: Point, b: Point, p: Point) -> float:
    """Signed perpendicular distance from p to the infinite line a->b.
    Positive = left of the direction a->b (in image coordinates, y down)."""
    length = distance(a, b)
    if length == 0:
        return 0.0
    return _orient(a, b, p) / length


def side_of_line(a: Point, b: Point, p: Point, margin: float = 0.0) -> int:
    """+1 left of a->b, -1 right, 0 within `margin` of the line (undecided)."""
    d = signed_distance_to_line(a, b, p)
    if d > margin:
        return 1
    if d < -margin:
        return -1
    return 0


def is_simple_polygon(polygon: Sequence[Point]) -> bool:
    """False when any two non-adjacent edges intersect (self-intersecting / bow-tie)."""
    n = len(polygon)
    if n < 3:
        return False
    edges = [(polygon[i], polygon[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if segments_intersect(edges[i][0], edges[i][1], edges[j][0], edges[j][1]):
                return False
    return True


def validate_polygon(points: Sequence[Sequence[float]], min_area: float = 0.001) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    problems: list[str] = []
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        return ["Points must be [x, y] pairs"]
    if len(pts) < 3:
        problems.append("A zone needs at least 3 points")
        return problems
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in pts):
        problems.append("All points must lie inside the frame (0..1)")
    if len({(round(x, 6), round(y, 6)) for x, y in pts}) < len(pts):
        problems.append("Duplicate points are not allowed")
    if polygon_area(pts) < min_area:
        problems.append("Zone is too small — draw a larger area")
    if not is_simple_polygon(pts):
        problems.append("Zone edges cross each other — redraw without overlaps")
    return problems


def validate_line(points: Sequence[Sequence[float]], min_length: float = 0.02) -> list[str]:
    problems: list[str] = []
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        return ["Points must be [x, y] pairs"]
    if len(pts) != 2:
        problems.append("A virtual line needs exactly 2 points")
        return problems
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in pts):
        problems.append("Both points must lie inside the frame (0..1)")
    if distance(pts[0], pts[1]) < min_length:
        problems.append("Line is too short")
    return problems
