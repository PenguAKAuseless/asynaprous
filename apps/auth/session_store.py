import uuid

# { "session_id_ngau_nhien": "username" }
_sessions = {}

def create_session(username):
    session_id = str(uuid.uuid4()) 
    _sessions[session_id] = username
    return session_id

def get_session_user(session_id):
    return _sessions.get(session_id)