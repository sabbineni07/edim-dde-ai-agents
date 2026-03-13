"""Factory for data collectors (local CSV, Databricks, etc.)."""

from typing import Optional

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Singleton instance
_collector_instance = None


class DataCollectorFactory:
    """Factory for creating data collector instances."""

    @staticmethod
    def get_collector(csv_path: Optional[str] = None):
        """Get the appropriate data collector based on settings.

        Args:
            csv_path: Optional override for local CSV path (used when use_local_data=True)

        Returns:
            DataCollector instance (LocalDataCollector or DatabricksCollector)
        """
        if settings.use_local_data:
            path = csv_path or settings.local_data_path
            logger.info("using_local_data_collector", csv_path=path)
            from DE.src.collectors.local_data_collector import LocalDataCollector

            return LocalDataCollector(csv_path=path)
        logger.info("using_databricks_collector")
        from DE.src.collectors.databricks_collector import DatabricksCollector

        return DatabricksCollector()


def get_data_collector(csv_path: Optional[str] = None):
    """Convenience function to get data collector. Uses singleton when possible."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = DataCollectorFactory.get_collector(csv_path)
    return _collector_instance


def reset_data_collector():
    """Reset cached collector (for testing)."""
    global _collector_instance
    _collector_instance = None
