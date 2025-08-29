# CRM Task Scheduling Setup

This guide explains how to set up **Celery** and **Celery Beat** for generating weekly CRM reports, along with required dependencies.

---

## 1. Install Dependencies

Install Redis and required Python packages:

```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install redis-server

# Install Python dependencies
pip install -r requirements.txt

✔ Install Redis & dependencies  
✔ Run migrations  
✔ Start Redis  
✔ Start Celery worker  
✔ Start Celery Beat  
✔ Verify logs