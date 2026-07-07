import argparse
import sys
from auth import create_user

def main():
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--username", required=True, help="The username for the admin")
    parser.add_argument("--password", required=True, help="The password for the admin")
    
    args = parser.parse_args()
    
    try:
        user = create_user(username=args.username, password=args.password, role="admin")
        print(f"Successfully created admin user: {user.username}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
