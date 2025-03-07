import sqlite3
import time
from datetime import datetime, timedelta
import os

def update_stalled_jobs():
    """Check for jobs that have been processing too long and mark them as failed"""
    conn = sqlite3.connect('image_jobs.db')
    cursor = conn.cursor()
    
    # Find jobs that have been processing for more than 5 minutes
    five_mins_ago = datetime.now() - timedelta(minutes=5)
    
    cursor.execute(
        "SELECT id FROM jobs WHERE status = 'processing' AND created_at < ?", 
        (five_mins_ago,)
    )
    
    stalled_jobs = cursor.fetchall()
    
    for job in stalled_jobs:
        job_id = job[0]
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?", 
            ("failed", datetime.now(), job_id)
        )
        print(f"Marked stalled job {job_id} as failed")
    
    conn.commit()
    conn.close()
    
    return len(stalled_jobs)

if __name__ == "__main__":
    while True:
        try:
            count = update_stalled_jobs()
            if count:
                print(f"Updated {count} stalled jobs")
        except Exception as e:
            print(f"Error in job monitor: {str(e)}")
        
        # Sleep for a minute
        time.sleep(60)