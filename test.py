import requests

# Register a new user
# register_response = requests.post('http://127.0.0.1:5000/register', 
#                                  json={'username': 'user1', 'password': 'password123'})

# Login to get token
login_response = requests.post('http://127.0.0.1:5000/login', 
                              json={'username': 'user1', 'password': 'password123'})
if login_response.status_code == 200:
    try:
        login_data = login_response.json()
        token = login_data['access_token']
    except requests.exceptions.JSONDecodeError:
        print("Failed to parse JSON response")
else:
    print(f"Login failed with status code {login_response.status_code}")
    login_response.raise_for_status()

# Use token for authenticated requests
headers = {'Authorization': f'Bearer {token}'}
generate_response = requests.post('http://127.0.0.1:5000/generate',
                                 json={'prompt': 'An astronaut riding a green horse'},
                                 headers=headers)
job_id = generate_response.json()['job_id']

# # Check status of your job
status_response = requests.get(f'http://127.0.0.1:5000/status/{job_id}', headers=headers)
print(status_response.json())