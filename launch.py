# HK Math Student Portal — Production Launcher
# Usage: python launch.py [--port 5100]

import sys, os
from pathlib import Path

# Add project root and question_bank to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"D:\S1\_question_bank")

from app import app

if __name__ == "__main__":
    port = int(sys.argv[2]) if "--port" in sys.argv and len(sys.argv) > sys.argv.index("--port") + 1 else 5100
    print(f"🚀 HK Math Student Portal @ http://localhost:{port}")
    print(f"   Adaptive Engine: ON")
    print(f"   AI Tutor: ON")
    print(f"   Mark Engine: ON")
    print(f"   DB: PostgreSQL question_bank")
    app.run(host="0.0.0.0", port=port, debug=False)
