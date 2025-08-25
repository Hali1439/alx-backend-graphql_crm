#!/usr/bin/env python3
import sys
import os
import datetime
import logging
import requests
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

# Setup logging
log_file = "/tmp/order_reminders_log.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s %(message)s")

def main():
    try:
        # GraphQL endpoint
        transport = RequestsHTTPTransport(
            url="http://localhost:8000/graphql",
            verify=False,
            retries=3,
        )

        client = Client(transport=transport, fetch_schema_from_transport=True)

        # Query: orders from last 7 days
        query = gql("""
        query GetRecentOrders {
            orders(orderDate_Gte: "%s") {
                id
                customer {
                    email
                }
            }
        }
        """ % (datetime.date.today() - datetime.timedelta(days=7)).isoformat())

        result = client.execute(query)

        orders = result.get("orders", [])
        for order in orders:
            log_msg = f"Reminder: Order {order['id']} for {order['customer']['email']}"
            logging.info(log_msg)

        print("Order reminders processed!")

    except Exception as e:
        logging.error(f"Error processing reminders: {e}")
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
