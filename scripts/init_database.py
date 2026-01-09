"""
Initialize the PostgreSQL database for Verified Financial Data AI System.

This is a DELEGATE to vfis/scripts/init_database.py which contains the 
full implementation including VFIS schema extensions.

USAGE:
    # Use SEED_TICKER env var
    SEED_TICKER=AAPL python -m scripts.init_database
    
    # Or run without seeding
    python -m scripts.init_database --no-seed
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import and run the full implementation
from vfis.scripts.init_database import main

if __name__ == "__main__":
    main()
