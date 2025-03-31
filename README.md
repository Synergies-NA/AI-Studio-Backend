# Introduction
This repository contains the backend server for handling AI model requests. It integrates three AI models: TripoSR for 2D-to-3D transformations, Stable Diffusion for text-to-image generation, and a custom model powered by ComfyUI for image-to-image transformations. The backend is built with Python and utilizes SQL, Redis, and Celery to manage tasks efficiently.

The server handles API requests, including database interactions and task queue management for AI model processing. Redis acts as the task manager, distributing jobs to Celery workers, which execute the AI model tasks. The system is designed to scale horizontally, allowing you to adjust the number of workers based on available hardware resources, enabling faster processing and support for more users.

The API is also secured by JWT authentication, ensuring that only authorized users can access the system.

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