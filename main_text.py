import os
import sys

import cv2
import numpy as np
import trimesh

from shapely.geometry import (
    Polygon,
    LineString,
    MultiPolygon,
    GeometryCollection,
)
from shapely.ops import nearest_points, unary_union


# =========================================================
# НАСТРОЙКИ
# =========================================================

DEFAULT_SIZE = 100.0
DEFAULT_HEIGHT = 10.0

WALL_THICKNESS = 1.2

RIM_HEIGHT = 2.0
RIM_WIDTH = 8.0

BRIDGE_WIDTH = 8.0

MIN_SIZE = 40.0
MAX_SIZE = 200.0

MIN_HEIGHT = 5.0
MAX_HEIGHT = 30.0


# =========================================================
# ПРОВЕРКА ВХОДНЫХ ДАННЫХ
# =========================================================

if len(sys.argv) < 2:
    print("Укажите файл изображения")
    sys.exit()


input_file = sys.argv[1]


if not os.path.exists(input_file):
    print("Файл не найден")
    sys.exit()


TARGET_SIZE = (
    float(sys.argv[2])
    if len(sys.argv) > 2
    else DEFAULT_SIZE
)


TOTAL_HEIGHT = (
    float(sys.argv[3])
    if len(sys.argv) > 3
    else DEFAULT_HEIGHT
)


if TARGET_SIZE < MIN_SIZE or TARGET_SIZE > MAX_SIZE:
    print(
        f"Размер должен быть от "
        f"{MIN_SIZE:.0f} до {MAX_SIZE:.0f} мм"
    )
    sys.exit()


if TOTAL_HEIGHT < MIN_HEIGHT or TOTAL_HEIGHT > MAX_HEIGHT:
    print(
        f"Высота должна быть от "
        f"{MIN_HEIGHT:.0f} до {MAX_HEIGHT:.0f} мм"
    )
    sys.exit()


# =========================================================
# ЗАГРУЖАЕМ ИЗОБРАЖЕНИЕ
# =========================================================

img = cv2.imread(
    input_file,
    cv2.IMREAD_UNCHANGED
)


if img is None:
    print("Не удалось открыть изображение")
    sys.exit()


# =========================================================
# ПРОЗРАЧНЫЙ PNG -> БЕЛЫЙ ФОН
# =========================================================

if len(img.shape) == 3 and img.shape[2] == 4:

    bgr = img[:, :, :3]

    alpha = (
        img[:, :, 3].astype(float)
        / 255.0
    )

    white = np.full_like(
        bgr,
        255
    )

    img = (
        bgr * alpha[:, :, None]
        +
        white * (1.0 - alpha[:, :, None])
    ).astype(np.uint8)


# =========================================================
# ПЕРЕВОД В СЕРЫЙ
# =========================================================

if len(img.shape) == 3:

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

else:

    gray = img


# =========================================================
# ЧЁРНО-БЕЛАЯ МАСКА
# =========================================================

_, binary = cv2.threshold(
    gray,
    0,
    255,
    cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
)


# =========================================================
# УБИРАЕМ МЕЛКИЙ МУСОР
# =========================================================

kernel = np.ones(
    (3, 3),
    np.uint8
)


binary = cv2.morphologyEx(
    binary,
    cv2.MORPH_OPEN,
    kernel
)


binary = cv2.morphologyEx(
    binary,
    cv2.MORPH_CLOSE,
    kernel
)


# =========================================================
# ЗЕРКАЛИМ ДЛЯ ПЕЧАТИ
# =========================================================

binary = cv2.flip(
    binary,
    1
)


# =========================================================
# ИЩЕМ КОНТУРЫ
# =========================================================

contours, hierarchy = cv2.findContours(
    binary,
    cv2.RETR_CCOMP,
    cv2.CHAIN_APPROX_NONE
)


if not contours or hierarchy is None:
    print("Контур не найден")
    sys.exit()


hierarchy = hierarchy[0]


# =========================================================
# ГЛАВНЫЙ ВНЕШНИЙ КОНТУР
# =========================================================

outer_candidates = []


for i, h in enumerate(hierarchy):

    if h[3] == -1:

        area = cv2.contourArea(
            contours[i]
        )

        if area > 20:
            outer_candidates.append(i)


if not outer_candidates:
    print("Внешний контур не найден")
    sys.exit()


outer_index = max(
    outer_candidates,
    key=lambda i: cv2.contourArea(
        contours[i]
    )
)


outer_contour = contours[
    outer_index
]


# =========================================================
# ВНУТРЕННИЕ ОТВЕРСТИЯ
# =========================================================

hole_contours = []


for i, h in enumerate(hierarchy):

    if h[3] == outer_index:

        area = cv2.contourArea(
            contours[i]
        )

        if area > 20:

            hole_contours.append(
                contours[i]
            )


print(
    "Найдено внутренних отверстий:",
    len(hole_contours)
)


# =========================================================
# ПРЕДПРОСМОТР
# =========================================================

preview = np.full(
    binary.shape,
    255,
    dtype=np.uint8
)


cv2.drawContours(
    preview,
    [outer_contour],
    -1,
    0,
    2
)


for hole in hole_contours:

    cv2.drawContours(
        preview,
        [hole],
        -1,
        0,
        2
    )


cv2.imwrite(
    f"output/{os.path.splitext(os.path.basename(input_file))[0]}_outline.png",
    preview
)


print(
    "Предпросмотр сохранён: "
    "output/text_outline.png"
)


# =========================================================
# МАСШТАБ
# =========================================================

x, y, w, h = cv2.boundingRect(
    outer_contour
)


scale = (
    TARGET_SIZE
    / max(w, h)
)


def contour_to_mm(contour):

    points = (
        contour[:, 0, :]
        .astype(float)
        * scale
    )

    points[:, 1] *= -1

    return points


outer_points = contour_to_mm(
    outer_contour
)


holes_points = []


for hole in hole_contours:

    holes_points.append(
        contour_to_mm(hole)
    )


# =========================================================
# ПОЛИГОН С ОТВЕРСТИЯМИ
# =========================================================

polygon = Polygon(
    outer_points,
    holes=[
        points.tolist()
        for points in holes_points
    ]
)


if not polygon.is_valid:
    polygon = polygon.buffer(0)


if polygon.is_empty:
    print("Ошибка геометрии")
    sys.exit()


# =========================================================
# РЕЖУЩАЯ СТЕНКА
# =========================================================

wall = polygon.boundary.buffer(
    WALL_THICKNESS / 2,
    join_style=2
)


# =========================================================
# ШИРОКИЙ БОРТИК
# =========================================================

rim = polygon.boundary.buffer(
    RIM_WIDTH / 2,
    join_style=2
)


# =========================================================
# ДВЕ ПЕРЕМЫЧКИ НА ОДНОЙ ПРЯМОЙ
# =========================================================

bridges = []


for interior in polygon.interiors:

    hole_polygon = Polygon(
        interior
    )


    if hole_polygon.is_empty:
        continue


    center = hole_polygon.centroid


    center_point, outer_point = nearest_points(
        center,
        polygon.exterior
    )


    dx = (
        outer_point.x
        - center.x
    )

    dy = (
        outer_point.y
        - center.y
    )


    length = (
        dx * dx
        + dy * dy
    ) ** 0.5


    if length == 0:
        continue


    ux = dx / length
    uy = dy / length


    minx, miny, maxx, maxy = (
        polygon.bounds
    )


    diagonal = (
        (maxx - minx) ** 2
        +
        (maxy - miny) ** 2
    ) ** 0.5


    line_length = (
        diagonal * 2
    )


    p1 = (
        center.x
        - ux * line_length,
        center.y
        - uy * line_length
    )


    p2 = (
        center.x
        + ux * line_length,
        center.y
        + uy * line_length
    )


    center_line = LineString(
        [p1, p2]
    )


    intersections = (
        center_line.intersection(
            polygon
        )
    )


    line_parts = []


    if isinstance(
        intersections,
        LineString
    ):

        line_parts = [
            intersections
        ]


    elif hasattr(
        intersections,
        "geoms"
    ):

        for geom in intersections.geoms:

            if isinstance(
                geom,
                LineString
            ):

                if geom.length > 0.5:

                    line_parts.append(
                        geom
                    )


    line_parts.sort(
        key=lambda line:
        line.distance(center)
    )


    selected_parts = (
        line_parts[:2]
    )


    for line_part in selected_parts:

        bridge = line_part.buffer(
            BRIDGE_WIDTH / 2,
            cap_style=2,
            join_style=2
        )


        bridges.append(
            bridge
        )


print(
    "Перемычек добавлено:",
    len(bridges)
)


if bridges:

    rim = unary_union(
        [rim] + bridges
    )


# =========================================================
# ЭКСТРУЗИЯ
# =========================================================

def extrude_geometry(
    geometry,
    height
):

    meshes = []


    if isinstance(
        geometry,
        Polygon
    ):

        meshes.append(
            trimesh.creation.extrude_polygon(
                geometry,
                height=height
            )
        )


    elif isinstance(
        geometry,
        MultiPolygon
    ):

        for geom in geometry.geoms:

            meshes.append(
                trimesh.creation.extrude_polygon(
                    geom,
                    height=height
                )
            )


    elif isinstance(
        geometry,
        GeometryCollection
    ):

        for geom in geometry.geoms:

            if isinstance(
                geom,
                Polygon
            ):

                meshes.append(
                    trimesh.creation.extrude_polygon(
                        geom,
                        height=height
                    )
                )


    if not meshes:

        raise ValueError(
            "Не удалось создать 3D-геометрию"
        )


    if len(meshes) == 1:

        return meshes[0]


    return trimesh.util.concatenate(
        meshes
    )


# =========================================================
# СОЗДАЁМ 3D
# =========================================================

wall_mesh = extrude_geometry(
    wall,
    TOTAL_HEIGHT + RIM_HEIGHT
)


rim_mesh = extrude_geometry(
    rim,
    RIM_HEIGHT
)


mesh = trimesh.util.concatenate(
    [
        wall_mesh,
        rim_mesh
    ]
)


# =========================================================
# ПРОВЕРКИ
# =========================================================

if round(
    mesh.extents[2],
    2
) != round(
    TOTAL_HEIGHT + RIM_HEIGHT,
    2
):

    print(
        "Ошибка: неверная высота модели"
    )

    sys.exit()


if mesh.volume <= 0:

    print(
        "Ошибка: модель не имеет объёма"
    )

    sys.exit()


# =========================================================
# СОХРАНЕНИЕ
# =========================================================

name = os.path.splitext(
    os.path.basename(
        input_file
    )
)[0]


output_file = (
    f"output/{name}.stl"
)


mesh.export(
    output_file
)


print(
    "Размер силуэта:",
    TARGET_SIZE,
    "мм"
)


print(
    "Высота режущей части:",
    TOTAL_HEIGHT,
    "мм"
)


print(
    "Размер модели:",
    mesh.extents
)


print(
    "Watertight:",
    mesh.is_watertight
)


print(
    "Файл сохранён:",
    output_file
)


print(
    "STL создан"
)