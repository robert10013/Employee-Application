# XYZ Employee Leave Management System
Flask + SQLite. Logins: admin/admin123, user1/user123, user2/user123

## Run locally
pip install -r requirements.txt && python app.py   # http://localhost:5000

## Run with Docker
docker compose up -d --build                        # http://localhost:5000
# On EC2: open inbound port 5000 in the security group.
