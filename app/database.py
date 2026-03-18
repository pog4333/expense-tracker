from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY

# Anon client — used for auth (login/logout)
# Respects Row Level Security — safe to use with user tokens
anon_client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Service client — used for all data operations from the backend
# Bypasses RLS — never expose this to the browser
service_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_db() -> Client:
    """Returns the service client for backend data operations."""
    return service_client
