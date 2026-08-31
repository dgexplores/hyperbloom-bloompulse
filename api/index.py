import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend.app.main import app
# Vercel expects `app` or `handler`
handler = app
