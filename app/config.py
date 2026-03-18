from dotenv import load_dotenv
import os

load_dotenv()

# Supabase
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY    = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# App
SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG      = os.getenv("DEBUG", "false").lower() == "true"

# Email backup
SMTP_HOST        = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT        = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER        = os.getenv("SMTP_USER", "")
SMTP_PASSWORD    = os.getenv("SMTP_PASSWORD", "")
BACKUP_EMAIL_TO  = os.getenv("BACKUP_EMAIL_TO", "")

# Web push
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL       = os.getenv("VAPID_EMAIL", "")
