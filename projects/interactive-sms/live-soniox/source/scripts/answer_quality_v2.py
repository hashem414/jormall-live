"""Bounded new revision verification. Keeps earlier run counters/results intact."""
import sys
from scripts import structure_live
from scripts.structure_journal import ROOT
structure_live.ROOT=ROOT/'answer-quality-v2'
structure_live.ROOT.mkdir(exist_ok=True)
if __name__=='__main__':raise SystemExit({'answers':structure_live.answers,'voice':structure_live.voice}[sys.argv[1]]())
