
# Dependencies:

* For text-to-picture Stable-Diffusion:
    * `pip install diffusers --upgrade`
    * `pip install invisible_watermark transformers accelerate safetensors`

* For TripoSR setup:
    In addition to the command mentioned on their md, also do `pip install --upgrade transformers accelerate`

* For backend server of HMLV AI Model:
`pip install flask flask-jwt-extended celery redis prometheus-client diffusers torch`

* Install Redis:
    * Ubuntu/Debian: sudo apt-get install redis-server
    * macOS: brew install redis
    * Windows: Download from the Redis website or use WSL

* Download Prometheus for tracking the task queue from [here](https://prometheus.io/download/) (optional) 
    * Copy the following to the prometheus.yml file:
        ```
        # my global config
        global:
        scrape_interval: 15s # Set the scrape interval to every 15 seconds. Default is every 1 minute.
        evaluation_interval: 15s # Evaluate rules every 15 seconds. The default is every 1 minute.
        # scrape_timeout is set to the global default (10s).

        # Alertmanager configuration
        alerting:
        alertmanagers:
            - static_configs:
                - targets:
                # - alertmanager:9093

        # Load rules once and periodically evaluate them according to the global 'evaluation_interval'.
        rule_files:
        # - "first_rules.yml"
        # - "second_rules.yml"

        # A scrape configuration containing exactly one endpoint to scrape:
        # Here it's Prometheus itself.
        scrape_configs:
        # The job name is added as a label `job=<job_name>` to any timeseries scraped from this config.
        - job_name: 'flask'
            metrics_path: '/metrics'
            basic_auth:
            username: 'admin'
            password: 'admin_password'

            # metrics_path defaults to '/metrics'
            # scheme defaults to 'http'.

            static_configs:
            - targets: ["localhost:8000"]
        ```

# Get it Running:

From the backend folder (current folder):
1. Get redis-server running: `redis-server`
2. Get Celery Workers running: `python celery_worker.py`
3. Run the Flask App: `python app.py`
From the prometheus folder:
4. If you have prometheus downloaded, cd to that directory and `./prometheus --config.file=prometheus.yml`


# Prometheus stats
Available stats are:
* `image_generation_requests_total`: Total number of image generation requests
* `image_generation_queue_size`: Size of the image generation queue
* `image_generation_processing_seconds`: Historgram for time spent processing each image generation


# Known issues:
* `image_generation_queue_size` is incorrect somehow. Tried inc() and dec(), saw the log message, but no change.