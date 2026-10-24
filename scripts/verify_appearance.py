"""Compatibility entrypoint for the current appearance/touch regression suite."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name('verify_touch_regression.py')), run_name='__main__')
