import contextlib
import aiohttp
import os
import json
from loguru import logger

class DashboardClient:
    def __init__(self, api_url=None, voice_url=None, enable_voice=True, session: aiohttp.ClientSession = None):
        # Default to internal docker-compose DNS name for backend
        self.api_url = api_url or os.getenv("DASHBOARD_API_URL", "http://backend:8000")
        self.voice_url = voice_url or os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.enable_voice = enable_voice
        self._session = session
        self._service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "")

    def _service_headers(self) -> dict:
        """Return headers for authenticated service-to-service calls."""
        return {"X-Service-Token": self._service_token} if self._service_token else {}

    @contextlib.asynccontextmanager
    async def _get_session(self):
        """Yield the shared session, or create an ephemeral one for standalone usage."""
        if self._session:
            yield self._session
        else:
            async with aiohttp.ClientSession() as session:
                yield session

    async def create_task(
        self,
        title: str,
        description: str,
        task_types: list[str] = None,
        expires_in_minutes: int = None,
        urgency: int = 2,
        zone: str = None,
        announce: bool = None,
        audience: str = "user",
        skill_level: str = None,
    ):
        """
        Create a new task in the dashboard.

        Args:
            title: Task title
            description: Task description
            task_types: List of task types (e.g., ['supply', 'urgent'])
            expires_in_minutes: Duration content should be displayed (minutes). If None, calculated based on types.
            urgency: Task urgency level (0-4)
            zone: Task location zone
            announce: Whether to announce via voice (default: True if voice enabled)
        """
        from datetime import datetime, timedelta, timezone

        if task_types is None:
            task_types = ["general"]

        if announce is None:
            announce = self.enable_voice and audience != "admin"

        # Determine expiration if not provided
        if expires_in_minutes is None:
            expires_in_minutes = 60 * 24 # Default 24h

            # Application specific rules
            if 'environment' in task_types: # e.g. lights on
                expires_in_minutes = min(expires_in_minutes, 60) # 1 hour max for env issues
            if 'supply' in task_types:
                expires_in_minutes = 60 * 24 * 7 # 1 week for supplies
            if 'urgent' in task_types:
                expires_in_minutes = min(expires_in_minutes, 30) # 30 mins for urgent

        # Calculate expires_at
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)).isoformat()

        url = f"{self.api_url}/tasks/"
        payload = {
            "title": title,
            "description": description,
            "task_type": task_types,
            "expires_at": expires_at,
            "location": zone or "Office",
            "urgency": urgency,
            "zone": zone,
            "audience": audience,
        }
        if skill_level:
            payload["skill_level"] = skill_level

        # Generate dual voice if enabled (before task creation)
        voice_data = None
        if announce:
            try:
                voice_data = await self._generate_dual_voice({
                    "title": title,
                    "description": description,
                    "location": zone or "Office",
                    "urgency": urgency,
                    "zone": zone
                })
                # Add voice data to payload
                if voice_data:
                    payload["announcement_audio_url"] = voice_data.get("announcement_audio_url")
                    payload["announcement_text"] = voice_data.get("announcement_text")
                    payload["completion_audio_url"] = voice_data.get("completion_audio_url")
                    payload["completion_text"] = voice_data.get("completion_text")
            except Exception as e:
                logger.warning(f"Failed to generate dual voice: {e}")

        try:
            async with self._get_session() as session:
                async with session.post(url, json=payload, headers=self._service_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Task created successfully: {data}")

                        if voice_data:
                            logger.info(f"Announcement: {voice_data.get('announcement_text')}")
                            logger.info(f"Completion: {voice_data.get('completion_text')}")

                        return data
                    else:
                        logger.error(f"Failed to create task: {response.status} {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error communicating with Dashboard API: {e}")
            return None

    async def get_active_tasks(self) -> list:
        """Fetch active (non-completed) tasks from dashboard."""
        url = f"{self.api_url}/tasks/"
        try:
            async with self._get_session() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        tasks = await response.json()
                        active = [
                            t for t in tasks
                            if not t.get("is_completed", False)
                        ]
                        return active
                    else:
                        logger.error(f"Failed to fetch tasks: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching active tasks: {e}")
            return []

    async def get_spatial_config(self):
        """Fetch merged spatial config (YAML + DB overrides) from backend.

        Returns SpatialConfig dataclass on success, None on failure.
        Caller should fall back to load_spatial_config() if this returns None.
        """
        from spatial_config import (
            SpatialConfig, BuildingConfig, ZoneGeometry, DevicePosition, CameraConfig
        )
        url = f"{self.api_url}/sensors/spatial/config"
        try:
            async with self._get_session() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning("Spatial config fetch failed: {}", resp.status)
                        return None
                    raw = await resp.json()

            config = SpatialConfig()

            bld = raw.get("building", {})
            config.building = BuildingConfig(
                name=bld.get("name", "SOMS Office"),
                width_m=bld.get("width_m", 15.0),
                height_m=bld.get("height_m", 10.0),
                floor_plan_image=bld.get("floor_plan_image"),
            )
            for zone_id, z in raw.get("zones", {}).items():
                config.zones[zone_id] = ZoneGeometry(
                    display_name=z.get("display_name", zone_id),
                    polygon=z.get("polygon", []),
                    area_m2=z.get("area_m2", 0.0),
                    floor=z.get("floor", 1),
                    adjacent_zones=z.get("adjacent_zones", []),
                    grid_cols=z.get("grid_cols", 10),
                    grid_rows=z.get("grid_rows", 10),
                )
            for dev_id, d in raw.get("devices", {}).items():
                config.devices[dev_id] = DevicePosition(
                    zone=d.get("zone", ""),
                    position=d.get("position", [0.0, 0.0]),
                    type=d.get("type", "sensor"),
                    channels=d.get("channels", []),
                    orientation_deg=d.get("orientation_deg"),
                    fov_deg=d.get("fov_deg"),
                    detection_range_m=d.get("detection_range_m"),
                    label=d.get("label", ""),
                )
            for cam_id, c in raw.get("cameras", {}).items():
                pos = c.get("position", [0.0, 0.0])
                config.cameras[cam_id] = CameraConfig(
                    zone=c.get("zone", ""),
                    position=pos[:2] if len(pos) >= 2 else [0.0, 0.0],
                    resolution=c.get("resolution", [640, 480]),
                    fov_deg=c.get("fov_deg", 90.0),
                    orientation_deg=c.get("orientation_deg", 0.0),
                )

            logger.info(
                "Spatial config fetched from backend: {} zones, {} devices, {} cameras",
                len(config.zones), len(config.devices), len(config.cameras),
            )
            return config

        except Exception as e:
            logger.warning("Could not fetch spatial config from backend: {}", e)
            return None

    async def add_shopping_item(
        self,
        name: str,
        category: str = None,
        quantity: int = 1,
        store: str = None,
        price: float = None,
        notes: str = None,
    ) -> dict | None:
        """Add an item to the shopping list via the Shopping API.

        The Shopping API handles duplicate prevention (merges quantity if
        the same item name already exists unpurchased).
        """
        url = f"{self.api_url}/shopping/"
        payload = {
            "name": name,
            "quantity": quantity,
            "priority": 2,
            "created_by": "brain",
        }
        if category:
            payload["category"] = category
        if store:
            payload["store"] = store
        if price is not None:
            payload["price"] = price
        if notes:
            payload["notes"] = notes

        try:
            async with self._get_session() as session:
                async with session.post(
                    url, json=payload, headers=self._service_headers()
                ) as response:
                    if response.status in (200, 201):
                        data = await response.json()
                        logger.info(f"Shopping item added: {name} x{quantity}")
                        return data
                    else:
                        logger.error(
                            f"Failed to add shopping item: {response.status} "
                            f"{await response.text()}"
                        )
                        return None
        except Exception as e:
            logger.error(f"Error adding shopping item: {e}")
            return None

    async def get_inventory_items(self) -> list[dict]:
        """Fetch active inventory items from the Inventory API.

        Returns a list of inventory item dicts, or empty list on failure.
        Used by InventoryTracker to load shelf→item mappings from DB.
        """
        url = f"{self.api_url}/inventory/?active_only=true"
        try:
            async with self._get_session() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        items = await response.json()
                        logger.info(f"Fetched {len(items)} inventory items from API")
                        return items
                    else:
                        logger.warning(f"Failed to fetch inventory items: {response.status}")
                        return []
        except Exception as e:
            logger.warning(f"Error fetching inventory items: {e}")
            return []

    async def push_inventory_status(self, items: list[dict]) -> bool:
        """Push live inventory status to Dashboard backend."""
        url = f"{self.api_url}/inventory/live-status"
        try:
            async with self._get_session() as session:
                async with session.put(
                    url, json=items,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Failed to push inventory status: {e}")
            return False

    async def get_task_stats(self) -> dict:
        """Fetch task statistics from dashboard."""
        url = f"{self.api_url}/tasks/stats"
        try:
            async with self._get_session() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Failed to fetch task stats: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error fetching task stats: {e}")
            return {}

    async def _generate_dual_voice(self, task_data: dict) -> dict:
        """
        Call voice service to generate both announcement and completion voices.

        Args:
            task_data: Task data

        Returns:
            Dict with announcement and completion audio URLs and texts
        """
        try:
            url = f"{self.voice_url}/api/voice/announce_with_completion"
            payload = {
                "task": task_data
            }

            async with self._get_session() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=180)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"Dual voice generated successfully")
                        return result
                    else:
                        logger.warning(f"Dual voice generation failed: {resp.status}")
                        return None

        except Exception as e:
            logger.warning(f"Failed to generate dual voice: {e}")
            return None
