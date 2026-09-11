from backend.core.geometry import (
    line_crossing_direction,
    point_in_polygon,
    polygon_area_normalized,
)

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


def test_point_inside_polygon():
    assert point_in_polygon((0.5, 0.5), SQUARE) is True


def test_point_outside_polygon():
    assert point_in_polygon((0.05, 0.05), SQUARE) is False


def test_point_outside_to_the_right():
    assert point_in_polygon((0.95, 0.5), SQUARE) is False


def test_polygon_area():
    assert abs(polygon_area_normalized(SQUARE) - 0.36) < 1e-9


def test_line_crossing_one_direction():
    line_a, line_b = (0.5, 0.0), (0.5, 1.0)
    direction = line_crossing_direction(line_a, line_b, (0.2, 0.5), (0.8, 0.5))
    assert direction in ("enter", "exit")


def test_line_crossing_opposite_direction_is_opposite_label():
    line_a, line_b = (0.5, 0.0), (0.5, 1.0)
    forward = line_crossing_direction(line_a, line_b, (0.2, 0.5), (0.8, 0.5))
    backward = line_crossing_direction(line_a, line_b, (0.8, 0.5), (0.2, 0.5))
    assert forward != backward
    assert {forward, backward} == {"enter", "exit"}


def test_no_crossing_when_not_intersecting():
    line_a, line_b = (0.5, 0.0), (0.5, 1.0)
    direction = line_crossing_direction(line_a, line_b, (0.1, 0.5), (0.3, 0.5))
    assert direction is None
