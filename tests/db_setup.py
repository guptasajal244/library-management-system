# tests/db_setup.py
#
# PURPOSE:
#   Initializes the database by creating tables and seeding default credentials.
#   Designed to wait for the MySQL service container to boot up in CI environments.

import sys
import os
import time

# Ensure the project root is in the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, db, User, Admin
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import OperationalError

def setup_database():
    print("Connecting to database and creating tables...")
    with app.app_context():
        # Retry database connection in case MySQL service container is still booting up
        for attempt in range(1, 31):
            try:
                # Create all tables if they do not exist
                db.create_all()
                print("Database tables created/verified successfully.")
                break
            except OperationalError as e:
                print(f"[{attempt}/30] Database connection not ready, retrying in 2 seconds... ({e})")
                time.sleep(2)
        else:
            print("Error: Could not connect to the database after 60 seconds. Exiting.")
            sys.exit(1)

        # Seed Admin User
        admin_username = "admin"
        admin_password = "admin"
        existing_admin = Admin.query.filter_by(username=admin_username).first()
        if not existing_admin:
            hashed_password = generate_password_hash(admin_password)
            new_admin = Admin(username=admin_username, password=hashed_password)
            db.session.add(new_admin)
            print(f"Seeded Admin: username='{admin_username}'")
        else:
            print(f"Admin '{admin_username}' already exists.")

        # Seed Regular User
        user_name = "Sajal"
        user_username = "sajal"
        user_password = "admin"
        existing_user = User.query.filter_by(username=user_username).first()
        if not existing_user:
            hashed_password = generate_password_hash(user_password)
            new_user = User(name=user_name, username=user_username, password=hashed_password)
            db.session.add(new_user)
            print(f"Seeded User: username='{user_username}'")
        else:
            print(f"User '{user_username}' already exists.")

        try:
            db.session.commit()
            print("Database initialization and seeding complete.")
        except Exception as e:
            db.session.rollback()
            print(f"Error during DB commit: {e}")
            sys.exit(1)

if __name__ == "__main__":
    setup_database()
