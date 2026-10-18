"""
gunicorn.conf.py - Gunicorn Production Server Configuration
Optimized for high concurrency, thread safety, and reverse proxy behind Nginx.
"""
import os
import multiprocessing

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Server Socket Binding
bind = "0.0.0.0:8000"
backlog = 2048

# Worker Processes & Concurrency
# Formula: (2 x $num_cores) + 1, capped for local stability
workers = min(4, multiprocessing.cpu_count() * 2 + 1)
worker_class = "gthread"
threads = 2
worker_connections = 1000
timeout = 60
keepalive = 5

# Memory Leak Prevention: Restart workers after serving requests
max_requests = 2000
max_requests_jitter = 100

# Logging
accesslog = os.path.join(LOG_DIR, "gunicorn_access.log")
errorlog = os.path.join(LOG_DIR, "gunicorn_error.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)ss'

# Process Naming
proc_name = "mednear_gunicorn"

# Reload on code changes in development if specified
reload = False
daemon = False
