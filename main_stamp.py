"""Shared-contour stamp: never re-detect the cutter silhouette."""
import os,sys,cv2,numpy as np,trimesh
from scipy.ndimage import gaussian_filter,gaussian_filter1d
from skimage.measure import marching_cubes
from shapely.geometry import Polygon

def largest(shape):
    if shape.is_empty:raise ValueError("Empty stamp contour")
    if shape.geom_type=="MultiPolygon":return max(shape.geoms,key=lambda p:p.area)
    if shape.geom_type!="Polygon":raise ValueError("Invalid stamp contour")
    return shape

def smooth(mask,area=3,external=False):
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL if external else cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
    out=[]
    for c in contours:
        if cv2.contourArea(c)<area or len(c)<8:continue
        pts=gaussian_filter1d(c[:,0,:].astype(float),sigma=1.6,axis=0,mode="wrap")
        pts=cv2.approxPolyDP(pts.astype(np.float32).reshape(-1,1,2),.35,True)[:,0,:]
        if len(pts)>=3:out.append(pts)
    return out

def generate(path,size=100,out=None):
    name=os.path.splitext(os.path.basename(path))[0]
    out=out or "output/"+name+"_stamp"
    os.makedirs(os.path.dirname(out) or ".",exist_ok=True)
    source=cv2.imread(path,cv2.IMREAD_COLOR)
    if source is None:raise ValueError("Cannot read source")
    contour_path=os.path.join("output",name+"_outline.npy")
    if not os.path.isfile(contour_path):raise ValueError("Prepare cutter first")
    vector=np.load(contour_path).astype(np.float32)
    if vector.ndim!=2 or vector.shape[1]!=2 or len(vector)<8:raise ValueError("Invalid cutter vector")
    h0,w0=source.shape[:2]
    bgr=cv2.flip(source,1)
    poly=largest(Polygon(vector).buffer(0))
    x,y,w,h=cv2.boundingRect(vector.reshape(-1,1,2))
    if min(w,h)<20:raise ValueError("Silhouette too small")
    scale=float(size)/max(w,h)
    pitch=.18
    width,height=int(np.ceil(w*scale/pitch)),int(np.ceil(h*scale/pitch))
    if width*height>1500000:raise ValueError("Stamp too large")
    roi=cv2.resize(bgr[y:y+h,x:x+w],(width,height),interpolation=cv2.INTER_AREA)
    def coords(pts):return np.rint((np.asarray(pts)-[x,y])*(scale/pitch)).astype(np.int32)
    silhouette=np.zeros((height,width),np.uint8)
    cv2.fillPoly(silhouette,[coords(poly.exterior.coords)],1)
    base_poly=largest(poly.buffer(-1.8/scale,join_style=1,resolution=24))
    base=np.zeros_like(silhouette)
    cv2.fillPoly(base,[coords(base_poly.exterior.coords)],1)
    if base.sum()<100:raise ValueError("Stamp base too small")
    lab=cv2.cvtColor(roi,cv2.COLOR_BGR2LAB)
    light=lab[:,:,0]
    aa=lab[:,:,1].astype(np.int16)
    bb=lab[:,:,2].astype(np.int16)
    valid=light[base>0]
    if len(valid)<100:raise ValueError("Empty interior")
    smoothed=cv2.GaussianBlur(light,(0,0),1.6)
    dark_limit=min(112,max(65,float(np.percentile(valid,15))))
    dark=((smoothed<dark_limit)&(base>0)).astype(np.uint8)
    dark=cv2.morphologyEx(dark,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(dark,8)
    dark_marks=np.zeros_like(dark)
    for i in range(1,count):
        area_mm=stats[i,cv2.CC_STAT_AREA]*pitch*pitch
        if 2<=area_mm<=150:dark_marks[labels==i]=1
    neutral=(np.abs(aa-128)<13)&(np.abs(bb-128)<19)
    bright_limit=max(205,float(np.percentile(valid,75)))
    bright=((light>bright_limit)&neutral&(base>0)).astype(np.uint8)
    bright=cv2.morphologyEx(bright,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(bright,8)
    light_lines=np.zeros_like(bright)
    light_islands=np.zeros_like(bright)
    for i in range(1,count):
        bx,by,bw,bh,area=stats[i]
        area_mm=area*pitch*pitch
        solidity=area/max(1,bw*bh)
        if 20<=area_mm<=2000 and solidity>.28:
            region=(labels==i).astype(np.uint8)
            light_islands|=region
            for pts in smooth(region,area=8,external=True):
                cv2.polylines(light_lines,[np.rint(pts).astype(np.int32)],True,1,max(2,round(1.2/pitch)),cv2.LINE_AA)
    clean=np.maximum(dark_marks,light_lines)
    clean=(gaussian_filter(clean.astype(float),sigma=1.0)>.42).astype(np.uint8)
    clean&=base
    cv2.imwrite(out+"_mask.png",255-clean*255)
    overlay=np.full((h0,w0,3),255,np.uint8)
    def to_full(pts):return np.rint(np.asarray(pts)*(pitch/scale)+[x,y]).astype(np.int32)
    for pts in smooth(light_islands,area=8,external=True):
        cv2.polylines(overlay,[to_full(pts)],True,(225,93,20),2,cv2.LINE_AA)
    for pts in smooth(dark_marks):
        cv2.fillPoly(overlay,[to_full(pts)],(225,93,20),cv2.LINE_AA)
    cv2.polylines(overlay,[np.rint(vector).astype(np.int32)],True,(0,145,255),2,cv2.LINE_AA)
    cv2.imwrite(out+"_preview.png",overlay)
    paths=[]
    for pts in smooth(clean):
        paths.append("M "+" L ".join(f"{px*pitch:.2f},{py*pitch:.2f}" for px,py in pts)+" Z")
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width*pitch:.2f}mm" height="{height*pitch:.2f}mm" viewBox="0 0 {width*pitch:.2f} {height*pitch:.2f}">'+''.join(f'<path d="{d}" fill="none" stroke="#1766cf" stroke-width=".5"/>' for d in paths)+'</svg>'
    with open(out+".svg","w") as file:file.write(svg)
    # The cutter cuts the perimeter; the stamp embosses only interior details.
    relief=clean
    volume=np.zeros((height+4,width+4,16),np.uint8)
    volume[2:-2,2:-2,1:9]=base[:,:,None]
    volume[2:-2,2:-2,9:14]=relief[:,:,None]
    verts,faces,_,_=marching_cubes(volume,.5,spacing=(pitch,pitch,pitch))
    # Export in EXACT cutter coordinates: global image origin, Y inverted.
    # Both STLs share one coordinate system, regardless of individual bounds.
    vertices=verts[:,[1,0,2]].copy()
    vertices[:,0]+=x*scale-2*pitch
    vertices[:,1]=-(vertices[:,1]+y*scale-2*pitch)
    mesh=trimesh.Trimesh(vertices=vertices,faces=faces[:,::-1],process=True)
    if not mesh.is_watertight or mesh.volume<=0:raise ValueError("Invalid stamp STL")
    mesh.export(out+".stl")
    return dict(watertight=mesh.is_watertight,extents=mesh.extents.tolist(),features=len(paths),output=out)

if __name__=="__main__":
    print(generate(sys.argv[1],float(sys.argv[2]) if len(sys.argv)>2 else 100,sys.argv[3] if len(sys.argv)>3 else None))