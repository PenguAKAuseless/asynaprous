"""Authentication helpers for assignment login flow."""

from .account_store import check_credentials_in_db, initialize_account_store


def check_credentials(auth_tuple):
    """Return True only when provided auth tuple matches database credentials."""
    if not auth_tuple or len(auth_tuple) != 2:
        return False

    username, password = auth_tuple
    return check_credentials_in_db(str(username), str(password))


initialize_account_store()