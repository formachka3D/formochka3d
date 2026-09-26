"""Safely enable website embossing in STAGING cutter generators.

This changes only /opt/formochka3d-staging/main.py and main_text.py.
Run after placing brand_rim.py in that staging directory.
Creates exact pre-change backups and refuses unknown source layouts.
"""
from pathlib import Path
import ast

ROOT = Path("/opt/formochka3d-staging")
MARKER = "# Brand website on broad non-cutting rim (staging)"
for filename, style in (("main.py", "outside"), ("main_text.py", "centered")):
    path = ROOT / filename
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print(filename, "already enabled")
        continue
    needle = """mesh = trimesh.util.concatenate(
    [
        wall_mesh,
        rim_mesh
    ]
)"""
    if source.count(needle) != 1:
        raise RuntimeError(f"Cannot find unique mesh assembly in {filename}; file unchanged")
    # Main generator scripts are run by the site with the staging root on sys.path.
    branded = f"""# Brand website on broad non-cutting rim (staging)
from brand_rim import brand_on_rim
parts = [wall_mesh, rim_mesh]
try:
    website_letters = brand_on_rim(polygon, rim, rim_style="{style}", rim_top_z=RIM_HEIGHT)
except Exception as exc:
    print("Website embossing skipped:", type(exc).__name__)
    website_letters = None
if website_letters is not None:
    parts.append(website_letters)
else:
    print("Website embossing: insufficient safe space on this outline")
mesh = trimesh.util.concatenate(parts)"""
    revised = source.replace(needle, branded, 1)
    ast.parse(revised)
    backup = ROOT / (filename + ".before_rim_brand_20260926")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(revised, encoding="utf-8")
    print(filename, "website embossing enabled")
