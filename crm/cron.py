import datetime
import requests

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

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

def check_graphql_hello():
    # Configure the transport
    transport = RequestsHTTPTransport(
        url="http://localhost:8000/graphql",  # adjust if your server runs elsewhere
        verify=True,
        retries=3,
    )

    client = Client(transport=transport, fetch_schema_from_transport=True)

    # Example query
    query = gql("""
    query {
        hello
    }
    """)

    try:
        response = client.execute(query)
        print("GraphQL hello response:", response)
    except Exception as e:
        print("GraphQL query failed:", str(e))

if __name__ == "__main__":
    check_graphql_hello()