# About
This is a backend server code that can handle 3 different AI models' requests concurrently: text-to-photo, 2D-to-3D transformation, AI photo style transformation. Depending on the available physical hardware limitation, you can configure how many workers can work concurrently.

AI model powered by StableDiffusion, TripSR and ComfyUI.

# Dependencies:

Install pyTorch here: https://pytorch.org/get-started/locally/

* For text-to-picture Stable-Diffusion model:
    * `pip install diffusers --upgrade`
    * `pip install invisible_watermark transformers accelerate safetensors`

* Download TripoSR and follow their setup
    * Note: place TripoSR at the same level as this directory. In other words, make it accessible from this directory by "../TripoSR"

* Clone the modified ComfyUI version that works with this server code [here](https://github.com/hrl-2024/ComfyUI.git).

* For backend server of HMLV AI Model:
`pip install flask flask-jwt-extended celery redis prometheus-client`

* Install Redis:
    * Ubuntu/Debian: sudo apt-get install redis-server
    * macOS: brew install redis
    * Windows: Download from the Redis website or use WSL

* Download Prometheus for tracking the task queue from [here](https://prometheus.io/download/) (optional) 
    * Copy the prometheus.yml file to the Prometheus folder.

# Get it Running:

From the backend folder (current folder):
1. Get redis-server running: `redis-server`
2. Run the Flask App: `python app.py`
3. Get Celery Workers running: `python celery_worker.py`
4. Get the job_monitor running: `python job_monitor.py`

From the prometheus folder (optional. If you decide to enable Prometheus):

5. If you have prometheus downloaded, cd to that directory and `./prometheus --config.file=prometheus.yml`


# Prometheus stats
Available stats are:
* `image_generation_requests_total`: Total number of image generation requests
* `image_generation_queue_size`: Size of the image generation queue
* `image_generation_processing_seconds`: Historgram for time spent processing each image generation


# Known issues:
* `image_generation_queue_size` is incorrect somehow. Tried inc() and dec(), saw the log message, but no change.