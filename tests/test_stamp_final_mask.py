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
            # The web download must scale the cached preview-matching STL,
            # not regenerate features at each slider setting.
            import trimesh
            cached = trimesh.load(f"output/{name}_stamp.stl", force="mesh", process=True)
            assert cached.is_watertight and cached.volume > 0
            original = cached.extents.copy()
            for requested_size in (40, 100, 200):
                resized = cached.copy()
                resized.vertices[:, 0:2] *= requested_size / 100
                assert resized.is_watertight
                assert np.allclose(
                    resized.extents[:2], original[:2] * requested_size / 100
                )
                assert np.isclose(resized.extents[2], original[2])
        finally:
            os.chdir(previous)


def test_size_reuses_prepared_details():
    # Preparation and STL generation must not independently re-detect details.
    with tempfile.TemporaryDirectory() as directory:
        previous = os.getcwd()
        os.chdir(directory)
        try:
            os.makedirs("input")
            os.makedirs("output")
            source = np.full((160,160,3), 220, np.uint8)
            cv2.circle(source,(45,45),12,(0,0,0),-1)
            cv2.imwrite("input/cached.png",source)
            contour=np.array([[5,5],[155,5],[155,155],[5,155],
                              [5,5],[5,5],[5,5],[5,5]],np.float32)
            np.save("output/cached_outline.npy",contour)
            # Deliberately different from the source so fresh segmentation
            # cannot accidentally satisfy the cached-mask assertion.
            canonical=np.full((500,500),255,np.uint8)
            cv2.circle(canonical,(250,250),65,0,-1)
            cv2.imwrite("output/cached_stamp_mask.png",canonical)
            result=generate("input/cached.png",40,"output/cached_resized")
            mask=cv2.imread("output/cached_resized_mask.png",0)==0
            resized=cv2.resize((canonical==0).astype(np.uint8),
                               (mask.shape[1],mask.shape[0]),
                               interpolation=cv2.INTER_NEAREST).astype(bool)
            assert mask.sum()>100
            assert not np.any(mask & ~resized)
            assert np.logical_and(mask,resized).sum()/resized.sum()>.90
            preview=cv2.imread("output/cached_resized_preview.png")
            orange=(preview[:,:,0]==225)&(preview[:,:,1]==93)&(preview[:,:,2]==20)
            assert np.array_equal(mask,orange)
            assert result["watertight"]
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    test_small_hole_cleanup()
    test_preview_and_stl_share_final_mask()
    print("PASS: hole cleanup, same-mask preview, watertight STL and XY scaling")
