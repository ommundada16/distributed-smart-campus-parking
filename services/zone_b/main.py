"""Zone B launcher — a separate OS process from Zone A / Zone C / the coordinator.

python -m services.zone_b.main
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from services.zone.zone_service import serve

if __name__ == "__main__":
    serve("B")
