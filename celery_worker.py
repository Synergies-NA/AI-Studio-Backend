from app import celery

# 1 worker on test environment
if __name__ == '__main__':
    celery.worker_main(['worker', '--loglevel=info', '--concurrency=1'])