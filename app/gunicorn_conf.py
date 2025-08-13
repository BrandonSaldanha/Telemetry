# app/gunicorn_conf.py
import multiprocessing
bind = "0.0.0.0:8080"
workers = max(2, multiprocessing.cpu_count() // 2)
worker_class = "uvicorn.workers.UvicornWorker"
graceful_timeout = 30
timeout = 60
accesslog = "-"    # stdout
errorlog = "-"     # stdout