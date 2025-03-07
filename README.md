
# Dependencies:

* For TripoSR setup:
    In addition to the command mentioned on their md, also do `pip install --upgrade transformers accelerate`


* For backend server of HMLV AI Model:
`pip install flask flask-jwt-extended celery redis prometheus-client diffusers torch`

* Install Redis:
    * Ubuntu/Debian: sudo apt-get install redis-server
    * macOS: brew install redis
    * Windows: Download from the Redis website or use WSL


# Get it Running:

1. Get redis-server running: `redis-server`
2. Get Celery Workers running: `python celery_worker.py`
3. Run the Flask App: `python app.py`

