"""ARTHUR MVP — push notification sender (Expo Push).

`send_push(title, body, data)` reads all registered device tokens from the
`push_tokens` table and POSTs each to the Expo push service. Everything is
wrapped in try/except: this function NEVER raises (a failed push must not
break task completion flows).

Imports only backend.database.db + requests (per contract).
"""
import requests

from backend.security.egress import EgressBlocked, check_outbound
from backend.security.secrets import scrub

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(title: str, body: str, data: dict | None = None) -> None:
    """Send a push notification to every registered device. Never raises."""
    try:
        from backend.database.db import get_conn

        conn = get_conn()
        try:
            rows = conn.execute("SELECT token FROM push_tokens").fetchall()
        except Exception:
            return  # table missing (Phase: mobile not registered yet) -> no-op
        finally:
            conn.close()

        payload_data = data or {}
        try:
            # Egress control: push delivery is an outbound send; the Expo
            # host must be on the allowlist (default: yes).
            check_outbound(EXPO_PUSH_URL, method="POST")
        except EgressBlocked:
            return
        for row in rows:
            token = row["token"]
            if not token:
                continue
            try:
                requests.post(
                    EXPO_PUSH_URL,
                    json={"to": token, "title": title, "body": body,
                          "data": payload_data},
                    timeout=10,
                )
            except Exception:
                continue  # one bad token must not stop the rest
    except Exception:
        return  # never raise
