#!/usr/bin/python3 -I
"""Entry point for ember-update.service (run as root)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ember.updater import main  # noqa: E402

sys.exit(main())
