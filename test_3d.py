import requests
import time

# Register a new user (uncomment if needed)
# register_response = requests.post('http://127.0.0.1:5000/register', 
#                                  json={'username': 'user1', 'password': 'password123'})
# print(register_response.json())

# Login to get token
login_response = requests.post('http://127.0.0.1:5000/login', 
                              json={'username': 'user1', 'password': 'password123'})
if login_response.status_code == 200:
    try:
        login_data = login_response.json()
        print(login_data)
        token = login_data['access_token']
    except requests.exceptions.JSONDecodeError:
        print("Failed to parse JSON response")
else:
    print(f"Login failed with status code {login_response.status_code}")
    login_response.raise_for_status()

# Use token for authenticated requests
headers = {'Authorization': f'Bearer {token}'}

# Upload an image
with open('../TripoSR/examples/chair.png', 'rb') as image_file:
    files = {'file': image_file}
    upload_response = requests.post('http://127.0.0.1:5000/upload', files=files, headers=headers)
    if upload_response.status_code == 200:
        upload_data = upload_response.json()
        print(upload_data)
        job_id = upload_data['job_id']
    else:
        print(f"Upload failed with status code {upload_response.status_code}")
        upload_response.raise_for_status()

# Check status of your job
while True:
    status_response = requests.get(f'http://127.0.0.1:5000/status/{job_id}', headers=headers)
    status_data = status_response.json()
    print(status_data)
    if status_data['status'] == 'completed':
        # Retrieve the result
        result_response = requests.get(f'http://127.0.0.1:5000/result/{job_id}', headers=headers)
        if result_response.status_code == 200:
            with open(f'result_{job_id}.zip', 'wb') as result_file:
                result_file.write(result_response.content)
            print(f"Result saved as result_{job_id}.zip")
        else:
            print(f"Failed to retrieve result with status code {result_response.status_code}")
            result_response.raise_for_status()
    elif status_data['status'] == 'failed':
        print(f"Job failed with error: {status_data['error']}")
        break
    time.sleep(5)  # Wait for 5 seconds before checking again