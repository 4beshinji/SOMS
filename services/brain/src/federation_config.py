"""
Federation configuration loader for SOMS multi-region deployment.

Loads region identity from config/federation.yaml. Used by Brain and
other services to tag events, decisions, and data with the region they
originated from. Phase 1: all defaults to "local".
"""
import os
from dataclasses import dataclass

import yaml
from loguru import logger


@dataclass
class RegionConfig:
    id: str = "local"
    display_name: str = "Local SOMS Instance"
    sovereign: bool = True
    timezone: str = "Asia/Tokyo"


@dataclass
class FederationConfig:
    region: RegionConfig = None

    def __post_init__(self):
        if self.region is None:
            self.region = RegionConfig()


_config: FederationConfig | None = None


def load_federation_config(path: str = "config/federation.yaml") -> FederationConfig:
    """Load federation configuration from YAML file.

    Falls back to defaults if the file doesn't exist.
    SOMS_REGION_ID env var overrides the YAML region.id.
    """
    global _config

    config = FederationConfig()

    if os.path.exists(path):
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}

        region = raw.get("region", {})
        config.region = RegionConfig(
            id=region.get("id", "local"),
            display_name=region.get("display_name", "Local SOMS Instance"),
            sovereign=region.get("sovereign", True),
            timezone=region.get("timezone", "Asia/Tokyo"),
        )
    else:
        logger.warning("Federation config not found at {}, using defaults", path)

    # Environment variable override
    env_region = os.getenv("SOMS_REGION_ID")
    if env_region:
        config.region.id = env_region
        logger.info("Region ID overridden by SOMS_REGION_ID: {}", env_region)

    logger.info(
        "Federation config loaded: region={}, display_name={}",
        config.region.id, config.region.display_name,
    )

    _config = config
    return config


def get_region_id() -> str:
    """Return the current region ID (module-level singleton)."""
    if _config is None:
        load_federation_config()
    return _config.region.id
