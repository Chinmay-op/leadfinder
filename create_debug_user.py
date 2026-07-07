from auth import create_user
try:
    create_user("debug", "debug", "admin")
    print("User debug created")
except Exception as e:
    print(e)
