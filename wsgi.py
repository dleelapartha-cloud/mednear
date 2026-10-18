"""
wsgi.py - Production WSGI Application Entry Point
Exposes the Flask app instance for high-concurrency WSGI servers (Gunicorn, uWSGI).
"""
import os
import sys

# Ensure mednear directory is in Python path
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if CUR_DIR not in sys.path:
    sys.path.insert(0, CUR_DIR)

from server import app

# Production application callable
application = app

if __name__ == "__main__":
    app.run()
