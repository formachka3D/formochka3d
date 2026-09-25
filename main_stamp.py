"""Isolated experimental stamp generator; never modifies cutter V3."""
import sys, os
import cv2
import numpy as np
from rembg import remove
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes
import trimesh
from shapely.geometry import Polygon

def generate(path, size=100, out=None):
    name=os.path.splitext(os.path.basename(path))[0]
    out=out or "output/"+name+"_stamp"
    os.makedirs(os.path.dirname(out) or ".",exist_ok=True)
    original=cv2.imread(path,cv2.IMREAD_UNCHANGED)
    if original is None: raise ValueError("Cannot read image")
    raw=open(path,"rb").read()
    rgba=cv2.imdecode(np.frombuffer(remove(raw),np.uint8),cv2.IMREAD_UNCHANGED)
    if rgba is None or rgba.ndim!=3 or rgba.shape[2]!=4: raise ValueError("No silhouette")
    alpha=rgba[:,:,3]
    fg=(alpha>128).astype(np.uint8)
    contours,_=cv2.findContours(fg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours: raise ValueError("No outer contour")
    outer=max(contours,key=cv2.contourArea)
    silhouette=np.zeros_like(fg);cv2.drawContours(silhouette,[outer],-1,1,-1)
    x,y,w,h=cv2.boundingRect(outer)
    if min(w,h)<20: raise ValueError("Silhouette too small")
    mm_per_px=float(size)/max(w,h)
    # Downsample to 0.30 mm voxels to bound resource use.
    pitch=.30
    width=max(2,int(np.ceil(w*mm_per_px/pitch)))
    height=max(2,int(np.ceil(h*mm_per_px/pitch)))
    target=(width,height)
    obj=cv2.resize(silhouette[y:y+h,x:x+w],target,interpolation=cv2.INTER_NEAREST)
    bgr=original[:,:,:3] if original.ndim==3 else cv2.cvtColor(original,cv2.COLOR_GRAY2BGR)
    if bgr.shape[:2]!=fg.shape:
        bgr=cv2.resize(bgr,(fg.shape[1],fg.shape[0]))
    roi=cv2.resize(bgr[y:y+h,x:x+w],target,interpolation=cv2.INTER_AREA)
    # Segment coherent material colors, not local shadows or image texture.
    lab=cv2.cvtColor(roi,cv2.COLOR_BGR2LAB)
    light=lab[:,:,0]
    a_chan=lab[:,:,1].astype(np.int16)
    b_chan=lab[:,:,2].astype(np.int16)
    # Strongly dark, solid connected marks (eyes, nose, mouth, printed lines).
    # A maximum physical area rejects the broad shadow along a cookie rim.
    smoothed=cv2.GaussianBlur(light,(0,0),1.4)
    valid=smoothed[obj>0]
    if len(valid)<100: raise ValueError("Too little foreground")
    dark_cutoff=min(112,max(65,float(np.percentile(valid,15))))
    dark=((smoothed<dark_cutoff)&(obj>0)).astype(np.uint8)
    dark=cv2.morphologyEx(dark,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(dark,8)
    marks=np.zeros_like(dark)
    for i in range(1,count):
        x0,y0,cw,ch,area=stats[i]
        physical_area=area*pitch*pitch
        if 2.5<=physical_area<=90 and cw*ch>0:
            marks[labels==i]=1
    # Light icing or painted islands are represented by their fine boundaries,
    # not filled solid or duplicated thick dark shadow bands.
    neutral=(np.abs(a_chan-128)<12)&(np.abs(b_chan-128)<18)
    bright_cutoff=max(210,float(np.percentile(light[obj>0],80)))
    light_regions=((light>bright_cutoff)&neutral&(obj>0)).astype(np.uint8)
    light_regions=cv2.morphologyEx(light_regions,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(light_regions,8)
    strokes=np.zeros_like(light_regions)
    for i in range(1,count):
        x0,y0,cw,ch,area=stats[i]
        physical_area=area*pitch*pitch
        solidity=area/max(1,cw*ch)
        if 10<=physical_area<=300 and solidity>.25:
            region=(labels==i).astype(np.uint8)
            contours,_=cv2.findContours(region,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(strokes,contours,-1,1,max(1,round(1.2/pitch)))
    # Keep the same clean binary geometry for the SVG, preview and STL.
    clean=np.maximum(marks,strokes)
    clean=(gaussian_filter(clean.astype(float),sigma=.65)>.40).astype(np.uint8)
    inset_px=max(2,round(2/pitch))
    base=cv2.erode(obj,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*inset_px+1,)*2))
    if base.sum()<100: raise ValueError("Base disappeared")
    clean=cv2.bitwise_and(clean,base)
    # Preserve original orientation in preview; stamp is mirrored for imprint.
    mask=(255-clean*255).astype(np.uint8)
    cv2.imwrite(out+"_mask.png",mask)
    overlay=cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR)
    cv2.drawContours(overlay,cv2.findContours(base,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],-1,(0,150,255),2)
    overlay[clean>0]=(255,120,20)
    cv2.imwrite(out+"_preview.png",overlay)
    paths=[]
    for contour in cv2.findContours(clean,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)[0]:
        if cv2.contourArea(contour)<3: continue
        pts=contour[:,0,:].astype(float)
        pts=cv2.approxPolyDP(pts.astype(np.float32).reshape(-1,1,2),.35,True)[:,0,:]
        if len(pts)<3: continue
        d="M "+" L ".join(f"{p[0]*pitch:.2f},{p[1]*pitch:.2f}" for p in pts)+" Z"
        paths.append(d)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width*pitch:.2f}mm" height="{height*pitch:.2f}mm" viewBox="0 0 {width*pitch:.2f} {height*pitch:.2f}">'+''.join(f'<path d="{d}" fill="#1766cf"/>' for d in paths)+'</svg>'
    open(out+".svg","w").write(svg)
    # Single watertight mesh from shared voxel volume, not overlapping solids.
    # Axis order y,x,z; mirror x for physical imprint.
    volume=np.zeros((height+4,width+4,15),np.uint8)
    volume[2:-2,2:-2,1:8]=base[:,::-1,None]
    volume[2:-2,2:-2,8:12]=clean[:,::-1,None]
    verts,faces,_,_=marching_cubes(volume,level=.5,spacing=(pitch,pitch,pitch))
    mesh=trimesh.Trimesh(vertices=verts[:,[1,0,2]],faces=faces,process=True)
    if not mesh.is_watertight or mesh.volume==0: raise ValueError("Non-watertight stamp")
    mesh.export(out+".stl")
    return dict(watertight=mesh.is_watertight,extents=mesh.extents.tolist(),features=len(paths),output=out)

if __name__=="__main__":
    print(generate(sys.argv[1],float(sys.argv[2]) if len(sys.argv)>2 else 100,sys.argv[3] if len(sys.argv)>3 else None))