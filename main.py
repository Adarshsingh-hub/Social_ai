"""main.py — Entry point. Run: python main.py"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", "5001"))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)