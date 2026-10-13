import math
import numpy as np

TIP_IDS = {"thumb":4,"index":8,"middle":12,"ring":16,"pinky":20}
PIP_IDS = {"index":6,"middle":10,"ring":14,"pinky":18}
MCP_IDS = {"index":5,"middle":9,"ring":13,"pinky":17}


def as_array(landmarks):
    return np.asarray([[p[0],p[1],p[2] if len(p)>2 else 0.0] for p in landmarks], dtype=float)

def distance(a,b): return float(np.linalg.norm(np.asarray(a)-np.asarray(b)))
def angle(a,b,c):
    ba=np.asarray(a)-np.asarray(b); bc=np.asarray(c)-np.asarray(b)
    denom=np.linalg.norm(ba)*np.linalg.norm(bc)
    if denom == 0: return 0.0
    return math.degrees(math.acos(float(np.clip(np.dot(ba,bc)/denom,-1,1))))

def finger_states(points):
    p=as_array(points)
    if len(p)!=21: return {k:False for k in ["thumb","index","middle","ring","pinky"]}
    wrist=p[0]
    states={}
    for name,tip in TIP_IDS.items():
        if name=="thumb":
            states[name] = distance(p[tip], p[5]) > distance(p[3], p[5]) * 1.08
        else:
            states[name] = distance(p[tip], wrist) > distance(p[PIP_IDS[name]], wrist) * 1.12
    return states

def normalize(points):
    p=as_array(points)
    if len(p)==0: return []
    origin=p[0].copy(); q=p-origin
    scale=np.max(np.linalg.norm(q[:,:2],axis=1)) or 1.0
    return (q/scale).tolist()
