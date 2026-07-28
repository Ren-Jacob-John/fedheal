"""
This module builds ON TOP OF module5-modelzoo rather than duplicating it —
SpecialistModel, PredictionResult, the base registry, and the router all
still live in module5. Importing this file first adds module5's folder to
sys.path so `from base import SpecialistModel` etc. work from here too.

Every file in this module that needs a module5 class imports `paths` first.
"""
import os
import sys

_MODULE5_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "module5-modelzoo"))
if _MODULE5_DIR not in sys.path:
    sys.path.insert(0, _MODULE5_DIR)
