"""Regression tests for final-mask stamp previews and selective hole cleanup."""
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main_stamp import fill_small_enclosed_holes, generate


def test_small_hole_cleanup():
    mask = np.ones((80, 80), np.uint8)
    mask[8:10, 8:10] = 0       # raster artifact: 0.13 mm^2 at pitch .18
    mask[30:45, 30:45] = 0   # deliberate 7.29 mm^2 opening
    mask[0:3, 60:70] = 0     # background-connected opening
    clean = fill_small_enclosed_holes(mask, pitch=.18)
    assert clean[8:10, 8:10].all()
    assert not clean[30:45, 30:45].any()
    assert not clean[0:3, 60:70].any()


def test_preview_and_stl_share_final_mask():
    with tempfile.TemporaryDirectory() as directory:
        previous = os.getcwd()
        os.chdir(directory)
        try:
            os.makedirs("input")
            os.makedirs("output")
            name = "testface"
            source = np.full((160, 160, 3), 220, np.uint8)
            cv2.circle(source, (60, 65), 12, (0, 0, 0), -1)
            cv2.circle(source, (100, 65), 12, (0, 0, 0), -1)
            cv2.circle(source, (80, 96), 7, (0, 0, 0), -1)
            cv2.rectangle(source, (65, 118), (95, 123), (0, 0, 0), -1)
            cv2.imwrite(f"input/{name}.png", source)
            # Same coordinate conventions as cutter's shared contour.
            contour = np.array(
                [[5,5], [155,5], [155,155], [5,155],
                 [5,5], [5,5], [5,5], [5,5]], np.float32
            )
            np.save(f"output/{name}_outline.npy", contour)
            result = generate(f"input/{name}.png", 40, f"output/{name}_stamp")
            mask = cv2.imread(f"output/{name}_stamp_mask.png", cv2.IMREAD_GRAYSCALE)
            preview = cv2.imread(f"output/{name}_stamp_preview.png")
            orange = (
                (preview[:, :, 0] == 225)
                & (preview[:, :, 1] == 93)
                & (preview[:, :, 2] == 20)
            )
            assert mask.shape == orange.shape
            assert np.array_equal(mask == 0, orange)
            assert result["watertight"]
            assert result["features"] >= 3
            assert os.path.isfile(f"output/{name}_stamp.stl")
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    test_small_hole_cleanup()
    test_preview_and_stl_share_final_mask()
    print("PASS: hole cleanup, same-mask preview, watertight STL")
