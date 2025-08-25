import datetime
import requests
from celery import shared_task

@shared_task
def generate_crm_report():
    """Fetch CRM stats via GraphQL and log weekly report."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = "/tmp/crm_report_log.txt"

    query = """
    query {
        customersCount
        ordersCount
        totalRevenue
    }
    """

    try:
        response = requests.post(
            "http://localhost:8000/graphql",
            json={"query": query},
            timeout=10,
        )
        data = response.json().get("data", {})

        customers = data.get("customersCount", 0)
        orders = data.get("ordersCount", 0)
        revenue = data.get("totalRevenue", 0)

        msg = f"{timestamp} - Report: {customers} customers, {orders} orders, {revenue} revenue"

    except Exception as e:
        msg = f"{timestamp} - Report generation failed: {e}"

    with open(log_file, "a") as f:
        f.write(msg + "\n")

    return msg
