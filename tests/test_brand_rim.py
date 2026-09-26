"""Geometry smoke test for raised website lettering on broad cutter rims."""
from shapely.geometry import Point, Polygon
from brand_rim import brand_on_rim

shapes = [
    ("round_large", Point(0, 0).buffer(50, resolution=80), "outside"),
    ("round_small", Point(0, 0).buffer(20, resolution=80), "outside"),
    ("square", Polygon([(-50, -50), (50, -50), (50, 50), (-50, 50)]), "outside"),
    ("text_style", Point(0, 0).buffer(50, resolution=80), "centered"),
]
for name, polygon, layout in shapes:
    if layout == "outside":
        rim = polygon.buffer(.6).buffer(8).difference(polygon.buffer(-.6))
    else:
        rim = polygon.boundary.buffer(4)
    brand = brand_on_rim(polygon, rim, rim_style=layout)
    assert brand is not None, f"Text not placed: {name}"
    assert brand.is_watertight and brand.volume > 0, name
    assert abs(brand.bounds[0][2] - 1.92) < .01, name
    assert abs(brand.bounds[1][2] - 2.5) < .01, name
    print("PASS", name, "triangles", len(brand.faces))
