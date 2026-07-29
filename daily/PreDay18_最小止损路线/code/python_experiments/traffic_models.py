from __future__ import annotations
import random

def periodic(count:int, mean:float)->list[float]:
    return [i*mean for i in range(count)]

def poisson(count:int, mean:float, seed:int)->list[float]:
    rng=random.Random(seed); out=[]; now=0.0
    for i in range(count):
        if i: now+=rng.expovariate(1.0/mean)
        out.append(now)
    return out

def burst(count:int, mean:float, *, burst_size:int=5, gap:float=.001)->list[float]:
    off=burst_size*mean-(burst_size-1)*gap
    if off<=0: raise ValueError("mean too small for frozen burst definition")
    out=[]; now=0.0
    while len(out)<count:
        for i in range(burst_size):
            if len(out)==count: break
            out.append(now+i*gap)
        now+=off+(burst_size-1)*gap
    return out
