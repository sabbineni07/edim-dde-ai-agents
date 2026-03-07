#!/usr/bin/env python3
"""Database migration script."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.database.connection import init_database, get_database_engine
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    """Run database migrations."""
    logger.info("starting_database_migration")
    
    try:
        # Initialize database (creates tables)
        init_database()
        logger.info("database_migration_complete")
        print("✅ Database migration completed successfully")
    except Exception as e:
        logger.error("database_migration_failed", error=str(e))
        print(f"❌ Database migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

