#!/usr/bin/python3 -I
"""Entry point for the Ember system service (run by systemd as root)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ember.daemon import main  # noqa: E402

sys.exit(main())
