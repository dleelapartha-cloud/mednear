"""
api/index.py - Vercel Serverless Entry Point for MedNear
Exposes the Flask WSGI application instance to the @vercel/python runtime.
"""
import sys
import os

# Add project root directory to Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server import app

# Vercel looks for 'app' or 'application'
application = app
