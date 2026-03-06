# gunicorn_config.py
bind = "0.0.0.0:5000"
workers = 4  # Количество процессов (обычно 2-4 × количество ядер)
threads = 2  # Потоков на процесс
worker_class = "gthread"
timeout = 30
max_requests = 1000
max_requests_jitter = 100