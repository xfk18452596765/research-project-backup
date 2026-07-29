"""Small dependency-free statistics helpers used by both result pipelines."""
from __future__ import annotations
import math, random, statistics

def percentile(values: list[float], q: float) -> float:
    if not values: return 0.0
    xs=sorted(float(v) for v in values); pos=(len(xs)-1)*q
    lo=int(pos); hi=min(lo+1,len(xs)-1); f=pos-lo
    return xs[lo]*(1-f)+xs[hi]*f

def summary(values: list[float]) -> dict[str,float|int]:
    xs=[float(v) for v in values]
    if not xs: return {"n":0,"mean":0.0,"sample_std":0.0,"median":0.0,"minimum":0.0,"maximum":0.0,"ci95_low":0.0,"ci95_high":0.0}
    mean=statistics.fmean(xs); sd=statistics.stdev(xs) if len(xs)>1 else 0.0
    half=1.96*sd/math.sqrt(len(xs)) if len(xs)>1 else 0.0
    return {"n":len(xs),"mean":mean,"sample_std":sd,"median":statistics.median(xs),"minimum":min(xs),"maximum":max(xs),"ci95_low":mean-half,"ci95_high":mean+half}

def paired_bootstrap_ci(values: list[float], *, seed: int=18018, samples: int=10000) -> tuple[float,float]:
    if not values: return 0.0,0.0
    rng=random.Random(seed); n=len(values)
    means=[statistics.fmean(values[rng.randrange(n)] for _ in range(n)) for _ in range(samples)]
    return percentile(means,.025),percentile(means,.975)

def jain(values: list[float]) -> float:
    if not values or sum(v*v for v in values)==0: return 0.0
    return sum(values)**2/(len(values)*sum(v*v for v in values))
