# app.py
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from celery import Celery
from celery.result import AsyncResult
from celery.signals import worker_shutdown, task_revoked, task_failure
import prometheus_client
from prometheus_client import Counter, Gauge, Histogram
import time
import os
import uuid
import sqlite3
from datetime import datetime, timedelta
import subprocess
import sys
from flask_cors import CORS

# Allowed extensions for image upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

OUTPUT_DIR_3D = '../TripoSR/uploads'
COMFY_UI_DIR = '../ComfyUI'

app = Flask(__name__, static_folder="dist", static_url_path="/")

# Enable CORS
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5173"],  # Allow only your frontend origin
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key')  # Change in production
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

# Configure Celery
app.config['broker_url'] = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app.config['result_backend'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
app.config['broker_connection_retry_on_startup'] = True

# Initialize JWT
jwt = JWTManager(app)

# Initialize Celery
celery = Celery(
    app.name,
    broker=app.config['broker_url'],
    backend=app.config['result_backend']
)
celery.conf.update(app.config)

# Create output directory if it doesn't exist
if not os.path.exists('output'):
    os.makedirs('output')

# Set up prometheus metrics
REQUESTS = Counter('image_generation_requests_total', 'Total number of image generation requests')
QUEUE_SIZE = Gauge('image_generation_queue_size', 'Size of the image generation queue')
QUEUE_SIZE.set(0)
PROCESSING_TIME = Histogram('image_generation_processing_seconds', 'Time spent processing image generation')

# Database initialization
def init_db():
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    
    # Create jobs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL DEFAULT 'image',
        prompt TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        completed_at TIMESTAMP,
        image_path TEXT,
        user_id TEXT NOT NULL
    )
    ''')
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin BOOLEAN NOT NULL DEFAULT 0
    )
    ''')
    
    # Create an admin user if it doesn't exist
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_id = str(uuid.uuid4())
        admin_password_hash = generate_password_hash('admin_password')  # Change in production
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (admin_id, 'admin', admin_password_hash, True)
        )
    
    conn.commit()
    conn.close()

init_db()

@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    print("Worker shutting down...")
    
@task_revoked.connect
def task_revoked_handler(request=None, terminated=False, signum=None, **kwargs):
    if terminated and request:
        job_id = request.args[0] if request.args else None
        if job_id:
            try:
                # Update the job status in the database
                conn = sqlite3.connect('image_jobs.db')
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?", 
                    ("failed", datetime.now(), job_id)
                )
                conn.commit()
                conn.close()
                print(f"Updated job {job_id} as failed due to task termination")
            except Exception as e:
                print(f"Failed to update database for job {job_id}: {str(e)}")

def get_queue_size():
    inspector = celery.control.inspect()
    active_tasks = inspector.active()
    queued_tasks = inspector.reserved()
    
    length = 0
    for tasks in active_tasks.values():
        length += len(tasks)
    for tasks in queued_tasks.values():
        length += len(tasks)
        
    return length

# Celery task for prompt-to-image generation
@celery.task(bind=True, max_retries=3, soft_time_limit=600)
def generate_image_task(self, job_id, prompt, user_id):
    try:
        # Update job status to processing
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", 
            ("processing", job_id)
        )
        conn.commit()
        conn.close()
        
        # Start monitoring processing time
        start_time = time.time()
        
        # Import here to avoid loading model in the web process
        from diffusers import DiffusionPipeline
        import torch
        import platform
        
        # Initialize the model
        pipe = DiffusionPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", 
            torch_dtype=torch.float16, 
            use_safetensors=True, 
            variant="fp16"
        )
        
        if platform.system() != "Darwin":
            pipe.to("cuda")
        else:
            pipe.to("mps")
            
        
        # Generate image
        image = pipe(prompt=prompt).images[0]
        
        # Save image
        image_path = f"output/{job_id}.png"
        image.save(image_path)
        
        # Record processing time
        processing_time = time.time() - start_time
        PROCESSING_TIME.observe(processing_time)
        
        # Update job as completed
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ?, image_path = ? WHERE id = ?", 
            ("completed", datetime.now(), image_path, job_id)
        )
        conn.commit()
        conn.close()
        
        return {"status": "completed", "image_path": image_path}
    
    except Exception as e:
        # Update job as failed
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?", 
            ("failed", datetime.now(), job_id)
        )
        conn.commit()
        conn.close()
        
        return {"status": "failed", "error": str(e)}
    finally:
        # Update gauge with current queue size
        print("Decrementing queue size")
        QUEUE_SIZE.dec(1)
        
# Celery task for 2D-to-3D model generation
@celery.task(bind=True, max_retries=3, soft_time_limit=600)
def generate_3d_model_task(self, job_id, file_path, user_id):
    try:
        # Update job status to processing
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", 
            ("processing", job_id)
        )
        conn.commit()
        conn.close()
        
        # Start monitoring processing time
        start_time = time.time()
        
        # Run the script for 2D-3D model
        print("Running 2D-to-3D script")
        script = "../TripoSR/run.py"
        
        output_dir = f"{OUTPUT_DIR_3D}/{job_id}"
        with app.app_context():
            process = subprocess.Popen(
                ["../TripoSR/.venv/bin/python", script, file_path, "--output-dir", output_dir],
                cwd="../TripoSR",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True  # Ensure the output is in text mode
            )
            
            # Read stdout in real time
            for line in process.stdout:
                print(line, end='')  # Print the output in real time
            
            process.stdout.close()
            process.wait()
            
            print("2D-to-3D Process completed")
            
            if process.returncode != 0:
                stderr = process.stderr.read()
                process.stderr.close()
                return {"status": "failed", "error": f"Failed to generate image: {stderr.strip()}"}
        
        # Record processing time
        processing_time = time.time() - start_time
        PROCESSING_TIME.observe(processing_time)
        
        # Update job as completed
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ?, image_path = ? WHERE id = ?", 
            ("completed", datetime.now(), output_dir + "/0/mesh.obj", job_id)
        )
        conn.commit()
        conn.close()
        
        return {"status": "completed", "output_dir": output_dir}
    
    except Exception as e:
        # Update job as failed
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?", 
            ("failed", datetime.now(), job_id)
        )
        conn.commit()
        conn.close()
        
        return {"status": "failed", "error": str(e)}
    finally:
        # Update gauge with current queue size
        print("Decrementing queue size")
        QUEUE_SIZE.dec(1)
        
# Celery task for ComfyUI
@celery.task(bind=True, max_retries=3, soft_time_limit=600)
def runComfyUI(self, job_id, file_name, user_id, type):
    try:
        # Update job status to processing
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", 
            ("processing", job_id)
        )
        conn.commit()
        conn.close()
        
        # Run the script for 2D-3D model
        print("Running 2D-to-2D script")
        script = f"{COMFY_UI_DIR}/{type}.py"
        
        output_dir = f"{COMFY_UI_DIR}/output/{type}_{job_id}_00001.png"
        with app.app_context():
            process = subprocess.Popen(
                [f"{COMFY_UI_DIR}/.venv/bin/python", script, file_name, job_id],
                cwd=f"{COMFY_UI_DIR}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True  # Ensure the output is in text mode
            )
            
            # Read stdout in real time
            for line in process.stdout:
                print(line, end='')  # Print the output in real time
            
            process.stdout.close()
            process.wait()
            
            print("{type} job sent to ComfyUI")
            
            if process.returncode != 0:
                stderr = process.stderr.read()
                process.stderr.close()
                return {"status": "failed", "error": f"Failed to generate image: {stderr.strip()}"}
        
        return {"status": "sent", "output_dir": output_dir}
    
    except Exception as e:
        # Update job as failed
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?", 
            ("failed", datetime.now(), job_id)
        )
        conn.commit()
        conn.close()
        
        return {"status": "failed", "error": str(e)}

@app.route("/")
def serve_react():
    return send_from_directory(app.static_folder, "index.html")

# Set up Prometheus metrics endpoint
@app.route('/api/metrics')
@jwt_required()
def metrics():
    user_id = get_jwt_identity()
    
    # Check if user is admin
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return jsonify({"error": "Unauthorized"}), 403
    
    return prometheus_client.generate_latest()

# Authentication routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Username and password are required"}), 400
    
    username = data['username']
    password = data['password']
    
    # Check if user already exists
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 409
    
    # Create new user
    user_id = str(uuid.uuid4())
    password_hash = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (id, username, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (user_id, username, password_hash, False)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"message": "User registered successfully"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Username and password are required"}), 400
    
    username = data['username']
    password = data['password']
    
    # Check credentials
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not check_password_hash(result[1], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    # Create access token
    access_token = create_access_token(identity=result[0])
    
    return jsonify({"access_token": access_token})

# Image generation API endpoints
@app.route('/api/generate', methods=['POST'])
@jwt_required()
def generate_image():
    user_id = get_jwt_identity()
    data = request.json
    
    if not data or 'prompt' not in data:
        return jsonify({'error': 'Prompt is required'}), 400
    
    prompt = data['prompt']
    job_id = str(uuid.uuid4())
    
    # Increment request counter
    REQUESTS.inc()
    
    # Increment queue size
    QUEUE_SIZE.inc()
    
    # Save job to database
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (id, prompt, status, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
        (job_id, prompt, "queued", datetime.now(), user_id)
    )
    conn.commit()
    conn.close()
    
    # Queue the Celery task
    task = generate_image_task.delay(job_id, prompt, user_id)
    
    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Image generation job has been queued'
    })
    
# Endpoint for uploading images
@app.route('/api/upload', methods=['POST'])
@jwt_required()
def upload_image():
    user_id = get_jwt_identity()
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    supported_types = ['3d_model', 'disney', 'sketch']
    
    if 'job_type' not in request.form or request.form['job_type'] not in supported_types:
        return jsonify({'error': 'Supported job type is required'}), 400
    
    file = request.files['file']
    job_type = request.form['job_type']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):        
        filename = secure_filename(file.filename)
        job_id = str(uuid.uuid4())
        
        # 3D model: Save job to database
        if job_type == '3d_model':
            file_path = os.path.join(OUTPUT_DIR_3D, job_id, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            
            # Increment request counter
            REQUESTS.inc()
            
            conn = sqlite3.connect('image_jobs.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO jobs (id, type, prompt, status, created_at, image_path, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, "3d_model", filename, "queued", datetime.now(), file_path, user_id)
            )
            conn.commit()
            conn.close()
            
            # Queue the Celery task
            task = generate_3d_model_task.delay(job_id, file_path, user_id)
            
            return jsonify({
                'job_id': job_id,
                'task_id': task.id,
                'status': 'queued',
                'message': '3D model generation job has been queued'
            })
        else:
            # store the image into ComfyUI's input folder
            file_path = os.path.join(COMFY_UI_DIR, "input", f"{job_id}.png")
            file.save(file_path)
                        
            output_path = f"{COMFY_UI_DIR}/output/{job_type}_{job_id}_00001_.png"
            print(f"Output path: {output_path}")
            
            conn = sqlite3.connect('image_jobs.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO jobs (id, type, prompt, status, created_at, image_path, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, job_type, filename, "queued", datetime.now(), output_path, user_id)
            )
            conn.commit()
            conn.close()
            
            # Queue the Celery task
            task = runComfyUI.delay(job_id, f"{job_id}.png", user_id, job_type)
            
            return jsonify({
                'job_id': job_id,
                'task_id': task.id,
                'status': 'queued',
                'message': f'{job_type} transformation job has been queued'
            })
    else:
        return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/status/<job_id>', methods=['GET'])
@jwt_required()
def get_status(job_id):
    user_id = get_jwt_identity()
    
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, status, created_at, completed_at, user_id FROM jobs WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Job not found'}), 404
    
    type, status, created_at, completed_at, job_user_id = result
    
    # Check if user owns this job
    if job_user_id != user_id:
        # Check if user is admin
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        admin_result = cursor.fetchone()
        conn.close()
        
        if not admin_result or not admin_result[0]:
            return jsonify({'error': 'Unauthorized access to this job'}), 403
    
    return jsonify({
        'job_id': job_id,
        'type': type,
        'status': status,
        'created_at': created_at,
        'completed_at': completed_at
    })

@app.route('/api/result/<job_id>', methods=['GET'])
@jwt_required()
def get_result(job_id):
    user_id = get_jwt_identity()
    
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, status, image_path, user_id FROM jobs WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Job not found'}), 404
    
    type, status, image_path, job_user_id = result
    
    # Check if user owns this job
    if job_user_id != user_id:
        # Check if user is admin
        conn = sqlite3.connect('image_jobs.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        admin_result = cursor.fetchone()
        conn.close()
        
        if not admin_result or not admin_result[0]:
            return jsonify({'error': 'Unauthorized access to this job'}), 403
    
    if status != 'completed':
        return jsonify({
            'job_id': job_id,
            'status': status,
            'message': f'Image generation is {status}'
        })
    
    if os.path.exists(image_path):
        if type == '3d_model':
            # Zip the output directory
            # Directly send the .obj file back
            return send_file(image_path, mimetype='application/octet-stream', as_attachment=True, download_name=f'{job_id}.obj')
        else:
            return send_file(image_path, mimetype='image/png')
    else:
        return jsonify({'error': 'Image file not found'}), 404
    
@app.route('/api/share/<job_id>', methods=['GET'])
def share_result(job_id):
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, status, image_path FROM jobs WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Job not found'}), 404
    
    type, status, image_path = result
    
    if status != 'completed':
        return jsonify({
            'job_id': job_id,
            'status': status,
            'message': f'Image generation is {status}'
        })
    
    if os.path.exists(image_path):
        if type == '3d_model':
            # send back the input image
            input_image_path = os.path.join(os.path.dirname(image_path), "input.png")
            if os.path.exists(input_image_path):
                return send_file(input_image_path, mimetype='image/png', as_attachment=True, download_name=f'{job_id}_input.png')
            else:
                return jsonify({'error': 'Input image file not found'}), 404
        elif type == 'image':
            return send_file(image_path, mimetype='image/png')
    else:
        return jsonify({'error': 'Image file not found'}), 404
    
@app.route('/api/retry/<job_id>', methods=['POST'])
@jwt_required()
def retry_job(job_id):
    user_id = get_jwt_identity()
    
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT prompt, status, user_id FROM jobs WHERE id = ?", (job_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    
    prompt, status, job_user_id = result
    
    # Check ownership or admin privileges
    if job_user_id != user_id:
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        admin_result = cursor.fetchone()
        if not admin_result or not admin_result[0]:
            conn.close()
            return jsonify({'error': 'Unauthorized access to this job'}), 403
    
    # Can only retry failed jobs
    if status != 'failed':
        conn.close()
        return jsonify({'error': f'Cannot retry job with status: {status}'}), 400
    
    # Update job status back to queued
    cursor.execute(
        "UPDATE jobs SET status = ?, completed_at = NULL, image_path = NULL WHERE id = ?",
        ("queued", job_id)
    )
    conn.commit()
    conn.close()
    
    # Queue the task again
    task = generate_image_task.delay(job_id, prompt, user_id)
    
    return jsonify({
        'job_id': job_id,
        'task_id': task.id,
        'status': 'queued',
        'message': 'Job has been requeued'
    })
    
@app.route('/api/jobs', methods=['GET'], strict_slashes=False)
@jwt_required()
def get_user_jobs():
    user_id = get_jwt_identity()
    job_type = request.args.get('type', None)  # Optional query parameter for filtering by type

    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()

    if job_type:
        if job_type == "pic_transform":
            cursor.execute(
                "SELECT id, type, prompt, status, created_at, completed_at FROM jobs WHERE user_id = ? AND type IN ('disney', 'sketch') ORDER BY created_at DESC",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT id, type, prompt, status, created_at, completed_at FROM jobs WHERE user_id = ? AND type = ? ORDER BY created_at DESC",
                (user_id, job_type)
            )
    else:
        cursor.execute(
            "SELECT id, type, prompt, status, created_at, completed_at FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )

    jobs = cursor.fetchall()
    conn.close()

    return jsonify({
        'jobs': [
            {
                'job_id': job[0],
                'type': job[1],
                'prompt': job[2],
                'status': job[3],
                'created_at': job[4],
                'completed_at': job[5]
            }
            for job in jobs
        ]
    })

# Admin endpoint to view all jobs
@app.route('/api/admin/jobs', methods=['GET'])
@jwt_required()
def admin_get_all_jobs():
    user_id = get_jwt_identity()
    
    # Check if user is admin
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result or not result[0]:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get all jobs
    cursor.execute("SELECT id, prompt, status, created_at, completed_at, user_id FROM jobs ORDER BY created_at DESC")
    jobs = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'jobs': [
            {
                'job_id': job[0],
                'prompt': job[1],
                'status': job[2],
                'created_at': job[3],
                'completed_at': job[4],
                'user_id': job[5]
            }
            for job in jobs
        ]
    })

if __name__ == '__main__':
    # Start prometheus on port 8000 (separate from Flask)
    prometheus_client.start_http_server(8000)
    app.run(debug=False, port=5001)