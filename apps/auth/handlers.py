# apps/auth/handlers.py

def check_credentials(auth_tuple):
    """
    Mục đích: Kiểm tra tài khoản người dùng.
    Lý thuyết: Nằm ở tầng Application Logic.
    """

    valid_users = {
        "admin": "123456",
        "user1": "password"
    }
    
    if not auth_tuple or len(auth_tuple) != 2:
        return False
        
    username, password = auth_tuple
    return valid_users.get(username) == password