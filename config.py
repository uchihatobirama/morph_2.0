import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_default_secret_key'
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', 'admin@example.com').split(',')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

