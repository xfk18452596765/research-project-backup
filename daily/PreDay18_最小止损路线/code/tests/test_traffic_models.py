from __future__ import annotations
import sys
from pathlib import Path
CODE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(CODE/'common'),str(CODE/'python_experiments')]
from traffic_models import periodic,poisson,burst

def main():
    assert periodic(3,.1)==[0.0,.1,.2]
    assert poisson(20,.02,7)==poisson(20,.02,7)
    assert poisson(20,.02,7)!=poisson(20,.02,17)
    xs=burst(200,.02); assert len(xs)==200
    assert abs((xs[-1]-xs[0])/(len(xs)-1)-.02)<.001
    print('traffic model tests passed')
if __name__=='__main__': main()
