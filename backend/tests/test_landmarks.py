from backend.vision.landmarks import normalize, distance

def test_distance(): assert distance([0,0,0],[3,4,0])==5

def test_normalize_origin():
    pts=[[0,0,0]]+[[1,0,0]]*20
    out=normalize(pts); assert out[0]==[0.0,0.0,0.0]
