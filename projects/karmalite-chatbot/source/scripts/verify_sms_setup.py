"""Read-only verification for the JOSMS integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import app
from app.db import close_pool, get_conn
from app.josms import configuration_status


with get_conn() as conn:
    groups = conn.execute(
        """
        SELECT status, kind, count(*) AS count,
               min(created_at) AS oldest, max(created_at) AS newest
        FROM notifications
        GROUP BY status, kind
        ORDER BY status, kind
        """
    ).fetchall()
    columns = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'notifications'
        ORDER BY ordinal_position
        """
    ).fetchall()

print("notification_groups=", groups)
print("notification_columns=", [row["column_name"] for row in columns])
print("sms_config=", configuration_status())
print(
    "routes=",
    sorted(
        route.path
        for route in app.routes
        if "notification" in route.path or "/sms/" in route.path
    ),
)
close_pool()
