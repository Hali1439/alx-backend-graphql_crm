import datetime
import requests

def log_crm_heartbeat():
    """Log CRM heartbeat and optionally ping GraphQL."""
    timestamp = datetime.datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
    log_file = "/tmp/crm_heartbeat_log.txt"

    try:
        # Optionally check GraphQL "hello" endpoint
        response = requests.post(
            "http://localhost:8000/graphql",
            json={"query": "{ hello }"},
            timeout=5,
        )
        if response.status_code == 200:
            msg = f"{timestamp} CRM is alive (GraphQL OK)"
        else:
            msg = f"{timestamp} CRM is alive (GraphQL ERROR {response.status_code})"
    except Exception as e:
        msg = f"{timestamp} CRM is alive (GraphQL unreachable: {e})"

    # Append to heartbeat log
    with open(log_file, "a") as f:
        f.write(msg + "\n")
