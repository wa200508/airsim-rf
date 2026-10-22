#!/usr/bin/env python3
"""Run the primary localhost RF dashboard from a checkout (stdlib launcher)."""
from pathlib import Path
import sys
# Load this stdlib-only module without importing the numerical package __init__.
import importlib.util
path=Path(__file__).resolve().parents[1]/'src/airsim_rf/dashboard.py'
spec=importlib.util.spec_from_file_location('rf_dashboard_launcher',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
# Dashboard uses filesystem assets when running without the installed package.
module.main()
