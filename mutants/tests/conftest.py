"""Disable the rate limiter before the app is imported.

The suite drives many requests from one client address, which the limiter
would otherwise reject partway through a run.
"""
import os

os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
