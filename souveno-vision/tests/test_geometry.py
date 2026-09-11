from src.analytics.geometry import (is_simple_polygon, point_in_polygon, polygon_area, segments_intersect, side_of_line,
                                    validate_line, validate_polygon)

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


def test_point_inside_and_outside_polygon():
    assert point_in_polygon((0.5, 0.5), SQUARE)
    assert not point_in_polygon((0.05, 0.05), SQUARE)
    assert not point_in_polygon((0.95, 0.5), SQUARE)
    assert not point_in_polygon((0.5, 0.95), SQUARE)


def test_point_on_edge_counts_as_inside():
    assert point_in_polygon((0.2, 0.5), SQUARE)


def test_concave_polygon():
    l_shape = [(0, 0), (1, 0), (1, 0.5), (0.5, 0.5), (0.5, 1), (0, 1)]
    assert point_in_polygon((0.25, 0.75), l_shape)
    assert not point_in_polygon((0.75, 0.75), l_shape)


def test_polygon_area_and_validation():
    assert abs(polygon_area(SQUARE) - 0.36) < 1e-9
    assert validate_polygon(SQUARE) == []
    assert validate_polygon([(0, 0), (1, 0)])  # too few points
    assert any("inside the frame" in p for p in validate_polygon([(0, 0), (1.2, 0), (1, 1)]))
    assert any("small" in p for p in validate_polygon([(0, 0), (0.001, 0), (0.001, 0.001)]))


def test_bowtie_polygon_is_rejected():
    bowtie = [(0, 0), (1, 1), (1, 0), (0, 1)]
    assert not is_simple_polygon(bowtie)
    assert any("cross" in p for p in validate_polygon(bowtie))


def test_line_validation():
    assert validate_line([(0.1, 0.5), (0.9, 0.5)]) == []
    assert validate_line([(0.1, 0.5)])
    assert validate_line([(0.1, 0.5), (0.101, 0.5)])


def test_segments_intersect_and_side():
    assert segments_intersect((0, 0), (1, 1), (0, 1), (1, 0))
    assert not segments_intersect((0, 0), (1, 0), (0, 1), (1, 1))
    a, b = (0.5, 0.0), (0.5, 1.0)
    assert side_of_line(a, b, (0.2, 0.5)) != side_of_line(a, b, (0.8, 0.5))
    assert side_of_line(a, b, (0.5, 0.5), margin=0.01) == 0
