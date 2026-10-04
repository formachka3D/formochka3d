"""Emboss formochka3d.ru on the wide, non-cutting rim of STL cutters.

Placement is verified against actual rim geometry. If no safe placement fits,
leave the STL unchanged rather than move text onto a blade or create floating bits.
"""
import math
import cv2
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

BRAND_TEXT = "formochka3d.ru"
RELIEF_HEIGHT_MM = 0.5


def _glyphs():
    font = ImageFont.load_default(size=144)
    bb = font.getbbox(BRAND_TEXT)
    pad = 12
    canvas = Image.new("L", (bb[2]-bb[0]+2*pad, bb[3]-bb[1]+2*pad))
    ImageDraw.Draw(canvas).text((pad-bb[0], pad-bb[1]), BRAND_TEXT,
                                font=font, fill=255)
    _, bitmap = cv2.threshold(np.asarray(canvas), 130, 255,
                              cv2.THRESH_BINARY)
    contours, meta = cv2.findContours(bitmap, cv2.RETR_CCOMP,
                                      cv2.CHAIN_APPROX_SIMPLE)
    if meta is None:
        raise ValueError("Branding font unavailable")
    meta = meta[0]
    glyphs = []
    for idx, ring in enumerate(contours):
        if meta[idx][3] != -1 or cv2.contourArea(ring) < 4:
            continue
        outer = cv2.approxPolyDP(ring, 0.65, True)[:, 0, :]
        holes = []
        child = meta[idx][2]
        while child >= 0:
            hole = contours[child]
            if len(hole) >= 3 and cv2.contourArea(hole) >= 4:
                holes.append(cv2.approxPolyDP(hole, 0.65, True)[:,0,:])
            child = meta[child][0]
        if len(outer) < 3:
            continue
        shape = Polygon(outer, holes)
        if not shape.is_valid:
            shape = shape.buffer(0)
        if shape.geom_type == "Polygon" and not shape.is_empty:
            glyphs.append(shape)
        elif shape.geom_type == "MultiPolygon":
            glyphs.extend(shape.geoms)
    if not glyphs:
        raise ValueError("No brand glyphs")
    xmin,ymin,xmax,ymax = unary_union(glyphs).bounds
    # Pillow's image Y points down; STL's Y points up.
    glyphs = [affinity.translate(affinity.scale(p, yfact=-1, origin=(0,0)),
                                xoff=-(xmin+xmax)/2, yoff=(ymin+ymax)/2)
              for p in glyphs]
    return glyphs, xmax-xmin, ymax-ymin


def brand_on_rim(outline, rim, *, rim_style, rim_top_z=2.0):
    """Build raised watertight glyphs, or None when there is no safe fit.

    Outside layout: 8 mm wide outer rim on image cutters.
    Centered layout: 8 mm total rim centered on text cutter outline.
    """
    if rim_style not in ("outside", "centered"):
        raise ValueError("Unknown rim style")
    if not isinstance(outline, Polygon) or outline.is_empty or rim.is_empty:
        return None
    outline = orient(outline, sign=1)
    path = outline.exterior
    if path.length < 20:
        return None
    glyphs, base_width, base_height = _glyphs()
    height = 3.4 if rim_style == "outside" else 2.35
    offset = 4.1 if rim_style == "outside" else 2.1
    safe_rim = rim.buffer(-0.18)
    if safe_rim.is_empty:
        return None
    for factor in (1.0, 0.9, 0.8, 0.7):
        scale = height * factor / base_height
        if height * factor < 1.6:
            continue
        scaled = [affinity.scale(p, xfact=scale, yfact=scale, origin=(0,0))
                  for p in glyphs]
        candidates = []
        for n in range(100):
            d = path.length * n / 100
            p1 = path.interpolate((d-0.9) % path.length)
            p2 = path.interpolate((d+0.9) % path.length)
            tx,ty = p2.x-p1.x,p2.y-p1.y
            norm = math.hypot(tx,ty)
            if norm < 0.1:
                continue
            tx,ty=tx/norm,ty/norm
            # CCW polygon: right normal points outside.
            nx,ny=ty,-tx
            if tx < -0.05:
                tx,ty=-tx,-ty
            mid = path.interpolate(d)
            angle = math.degrees(math.atan2(ty,tx))
            candidates.append((abs(ty),angle,mid.x+nx*offset,mid.y+ny*offset))
        for _,angle,cx,cy in sorted(candidates, key=lambda t:t[0]):
            moved = [affinity.translate(affinity.rotate(p,angle,origin=(0,0)),
                                        xoff=cx,yoff=cy) for p in scaled]
            if not safe_rim.covers(unary_union(moved)):
                continue
            meshes = []
            for glyph in moved:
                solid = trimesh.creation.extrude_polygon(
                    glyph, height=RELIEF_HEIGHT_MM+0.08)
                solid.apply_translation((0,0,rim_top_z-0.08))
                meshes.append(solid)
            if meshes:
                result = trimesh.util.concatenate(meshes)
                if result.is_watertight and result.volume>0:
                    return result
    return None
