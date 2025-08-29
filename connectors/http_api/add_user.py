#!/usr/bin/env python3
"""
Quick script to add a user to the auth database for dev/demo.
Usage:
  python connectors/http_api/add_user.py <username> <password>
"""
import sys
from connectors.http_api import auth

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python connectors/http_api/add_user.py <username> <password>")
        sys.exit(1)
    username, password = sys.argv[1], sys.argv[2]
    auth.create_user_table()
    auth.add_user(username, password)
    print(f"User '{username}' added.")
