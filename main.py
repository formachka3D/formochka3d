from skimage import measure
import numpy as np

from rembg import remove

import cv2
import trimesh
from shapely.geometry import Polygon
import sys
import os


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


# Размер силуэта
TARGET_SIZE = (
    float(sys.argv[2])
    if len(sys.argv) > 2
    else 100.0
)


# Высота режущей стенки
TOTAL_HEIGHT = (
    float(sys.argv[3])
    if len(sys.argv) > 3
    else 10.0
)


if TARGET_SIZE < 40 or TARGET_SIZE > 200:
    print("Размер должен быть от 40 до 200 мм")
    sys.exit()


if TOTAL_HEIGHT < 5 or TOTAL_HEIGHT > 30:
    print("Высота должна быть от 5 до 30 мм")
    sys.exit()


# =========================================================
# ПОСТОЯННЫЕ ПАРАМЕТРЫ
# =========================================================

WALL_THICKNESS = 1.2

RIM_HEIGHT = 2.0
RIM_WIDTH = 8.0


# =========================================================
# УДАЛЯЕМ ФОН
# =========================================================

with open(input_file, "rb") as f:
    input_bytes = f.read()


result_bytes = remove(input_bytes)


# Decode the per-request background-removal result in memory.
# A shared temporary file would mix images from concurrent users.
img = cv2.imdecode(
    np.frombuffer(result_bytes, dtype=np.uint8),
    cv2.IMREAD_UNCHANGED
)


if img is None:
    print("Не удалось открыть изображение")
    sys.exit()


if len(img.shape) == 3 and img.shape[2] == 4:

    binary = img[:, :, 3]

else:

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    _, binary = cv2.threshold(
        gray,
        127,
        255,
        cv2.THRESH_BINARY_INV
    )


# Зеркалим модель для печати
binary = cv2.flip(
    binary,
    1
)


# =========================================================
# ВЕКТОРНЫЙ КОНТУР
# =========================================================

vector_contours = measure.find_contours(
    binary.astype(float) / 255.0,
    0.5
)


if not vector_contours:
    print("Контур не найден")
    sys.exit()


vector = max(
    vector_contours,
    key=len
)


vector_points = np.column_stack(
    (
        vector[:, 1],
        vector[:, 0]
    )
).astype(np.float32)


# =========================================================
# ПРЕДПРОСМОТР
# =========================================================

preview_points = vector_points.astype(
    np.int32
)


vector_preview = np.full(
    binary.shape,
    255,
    dtype=np.uint8
)


cv2.polylines(
    vector_preview,
    [preview_points],
    True,
    0,
    2
)


cv2.imwrite(
    f"output/{os.path.splitext(os.path.basename(input_file))[0]}_outline.png",
    vector_preview
)


print(
    "Контур сохранён: "
    "output/vector_outline.png"
)


# =========================================================
# МАСШТАБ
# =========================================================

contour = vector_points.reshape(
    (-1, 1, 2)
)


x, y, w, h = cv2.boundingRect(
    contour
)


scale = TARGET_SIZE / max(
    w,
    h
)


points_mm = (
    contour[:, 0, :]
    .astype(float)
    * scale
)


points_mm[:, 1] *= -1


# =========================================================
# СОЗДАЁМ ПОЛИГОН
# =========================================================

polygon = Polygon(
    points_mm
)


if not polygon.is_valid:
    polygon = polygon.buffer(0)


if polygon.is_empty:
    print("Ошибка геометрии")
    sys.exit()


# =========================================================
# РЕЖУЩАЯ СТЕНКА
# =========================================================

outer = polygon.buffer(
    WALL_THICKNESS / 2
)


inner = polygon.buffer(
    -WALL_THICKNESS / 2
)


wall = outer.difference(
    inner
)


# =========================================================
# ШИРОКИЙ БОРТИК
#
# Только наружу.
# Внутреннее пространство остаётся свободным.
# =========================================================

rim_outer = outer.buffer(
    RIM_WIDTH
)


rim = rim_outer.difference(
    inner
)


# =========================================================
# СОЗДАЁМ 3D
# =========================================================

wall_mesh = (
    trimesh.creation.extrude_polygon(
        wall,
        height=TOTAL_HEIGHT + RIM_HEIGHT
    )
)


rim_mesh = (
    trimesh.creation.extrude_polygon(
        rim,
        height=RIM_HEIGHT
    )
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


if not mesh.is_watertight:

    print(
        "Ошибка: STL не замкнут"
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
    "Высота:",
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