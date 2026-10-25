"""Four-point planar homography for manually annotated football-field landmarks.

This is geometry only, not automatic video calibration or validated camera tracking.
"""
from __future__ import annotations
import math

def solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n=len(b)
    if len(a)!=n or any(len(row)!=n for row in a):
        raise ValueError("invalid matrix")
    m=[list(map(float,row))+[float(b[i])] for i,row in enumerate(a)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda i:abs(m[i][col]))
        if abs(m[pivot][col])<1e-10: raise ValueError("degenerate landmark configuration")
        m[col],m[pivot]=m[pivot],m[col]
        d=m[col][col]
        m[col]=[v/d for v in m[col]]
        for row in range(n):
            if row==col:continue
            f=m[row][col]
            m[row]=[v-f*w for v,w in zip(m[row],m[col])]
    return [m[i][-1] for i in range(n)]

def fit_homography(source: list[tuple[float,float]],target: list[tuple[float,float]]) -> tuple[float,...]:
    if len(source)!=4 or len(target)!=4:raise ValueError("exactly four correspondences required")
    if not all(math.isfinite(v) for p in source+target for v in p):raise ValueError("nonfinite landmark")
    a=[];b=[]
    for (x,y),(u,v) in zip(source,target):
        a.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
        b.extend([u,v])
    return tuple(solve_linear(a,b))+(1.,)

def project(h: tuple[float,...],point: tuple[float,float]) -> tuple[float,float]:
    if len(h)!=9 or not all(math.isfinite(v) for v in h+tuple(point)):raise ValueError("invalid homography or point")
    x,y=point
    d=h[6]*x+h[7]*y+h[8]
    if abs(d)<1e-10:raise ValueError("point at infinity")
    return ((h[0]*x+h[1]*y+h[2])/d,(h[3]*x+h[4]*y+h[5])/d)
