#!/bin/bash
# clean_inactive_customers.sh
# Deletes customers with no orders in the past year and logs results.

deleted_count=$(python manage.py shell -c "
from django.utils import timezone
from datetime import timedelta
from crm.models import Customer

cutoff_date = timezone.now() - timedelta(days=365)
inactive_customers = Customer.objects.exclude(orders__created_at__gte=cutoff_date)
count = inactive_customers.count()
inactive_customers.delete()
print(count)
")

echo "$(date): Deleted $deleted_count inactive customers" >> /tmp/customer_cleanup_log.txt