"""Authentication helpers for assignment login flow."""

VALID_USERS = {
    "admin": "123456",
    "user1": "password",
}


def check_credentials(auth_tuple):
    """Return True only when provided auth tuple matches known credentials."""
    if not auth_tuple or len(auth_tuple) != 2:
        return False

    username, password = auth_tuple
    return VALID_USERS.get(str(username)) == str(password)