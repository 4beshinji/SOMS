"""
Tool Executor: Routes tool calls through Sanitizer validation to handlers.
"""
import json
import os
from typing import Dict, Any
import aiohttp
from loguru import logger


class ToolExecutor:
    def __init__(self, sanitizer, mcp_bridge, dashboard_client, world_model, task_queue, session: aiohttp.ClientSession = None, device_registry=None, inventory_tracker=None, calibration_manager=None):
        self.sanitizer = sanitizer
        self.mcp = mcp_bridge
        self.dashboard = dashboard_client
        self.world_model = world_model
        self.task_queue = task_queue
        self._session = session
        self.device_registry = device_registry
        self.inventory_tracker = inventory_tracker
        self.calibration_manager = calibration_manager
        self.voice_url = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
        self.dashboard_api_url = os.getenv("DASHBOARD_API_URL", "http://backend:8000")
        self._service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "")

    def _service_headers(self) -> dict:
        """Return headers for authenticated service-to-service calls."""
        return {"X-Service-Token": self._service_token} if self._service_token else {}

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call with validation.

        Returns:
            {"success": True, "result": "..."} or {"success": False, "error": "..."}
        """
        # Validate through Sanitizer
        is_safe, reason = self.sanitizer.validate_tool_call(tool_name, arguments)
        if not is_safe:
            logger.warning(f"Tool call REJECTED: {tool_name} - {reason}")
            return {"success": False, "error": reason}

        try:
            if tool_name == "create_task":
                return await self._handle_create_task(arguments)
            elif tool_name == "send_device_command":
                return await self._handle_device_command(arguments)
            elif tool_name == "speak":
                return await self._handle_speak(arguments)
            elif tool_name == "get_zone_status":
                return await self._handle_get_zone_status(arguments)
            elif tool_name == "get_active_tasks":
                return await self._handle_get_active_tasks()
            elif tool_name == "get_device_status":
                return await self._handle_get_device_status(arguments)
            elif tool_name == "check_inventory":
                return await self._handle_check_inventory(arguments)
            elif tool_name == "add_shopping_item":
                return await self._handle_add_shopping_item(arguments)
            elif tool_name == "calibrate_shelf":
                return await self._handle_calibrate_shelf(arguments)
            elif tool_name == "trigger_display_event":
                return await self._handle_trigger_display_event(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task via DashboardClient and register with TaskQueueManager."""
        title = args.get("title", "")
        description = args.get("description", "")
        bounty = args.get("bounty", 1000)
        urgency = args.get("urgency", 2)
        zone = args.get("zone")
        audience = args.get("audience", "user")

        # Parse task_types from comma-separated string
        task_types_str = args.get("task_types", "general")
        task_types = [t.strip() for t in task_types_str.split(",") if t.strip()]

        result = await self.dashboard.create_task(
            title=title,
            description=description,
            bounty=bounty,
            urgency=urgency,
            zone=zone,
            task_types=task_types,
            audience=audience,
        )

        if result and result.get("id"):
            task_id = result["id"]

            # Record successful creation for rate limiting
            self.sanitizer.record_task_created()

            # Register with TaskQueueManager for scheduling
            if self.task_queue:
                await self.task_queue.add_task(
                    task_id=task_id,
                    title=title,
                    urgency=urgency,
                    zone=zone,
                )

            return {
                "success": True,
                "result": f"タスク '{title}' を作成しました (ID: {task_id}, 報酬: {bounty}pt)",
            }
        else:
            return {"success": False, "error": "タスクの作成に失敗しました"}

    async def _handle_speak(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize speech and record as ephemeral voice event."""
        message = args.get("message", "")
        zone = args.get("zone")
        tone = args.get("tone", "neutral")

        # 1. Call voice service to synthesize text directly
        audio_url = None
        try:
            async with self._session.post(
                f"{self.voice_url}/api/voice/synthesize",
                json={"text": message},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    audio_url = data.get("audio_url")
                else:
                    logger.warning(f"Voice synthesize failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Voice synthesize error: {e}")

        # 2. Record voice event in dashboard backend
        try:
            await self._session.post(
                f"{self.dashboard_api_url}/voice-events/",
                json={
                    "message": message,
                    "audio_url": audio_url or "",
                    "zone": zone,
                    "tone": tone,
                },
                headers=self._service_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            )
        except Exception as e:
            logger.warning(f"Failed to record voice event: {e}")

        # Record successful speak for cooldown tracking (H-5 fix)
        self.sanitizer.record_speak(zone=zone or "general")

        return {
            "success": True,
            "result": f"「{message}」を音声で通知しました",
        }

    async def _handle_device_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to edge device via MCPBridge with adaptive timeout."""
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")

        # Parse arguments (may be JSON string or dict)
        inner_args = args.get("arguments", "{}")
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (json.JSONDecodeError, TypeError):
                inner_args = {}

        # Adaptive timeout from DeviceRegistry
        timeout = None
        if self.device_registry:
            timeout = self.device_registry.get_timeout_for_device(agent_id)

        result = await self.mcp.call_tool(agent_id, tool_name, inner_args, timeout=timeout)

        # Handle queued responses (command queued for sleeping device)
        if isinstance(result, dict) and result.get("status") == "queued":
            target = result.get("target", agent_id)
            return {
                "success": True,
                "result": f"コマンドをキューに追加: {target}/{tool_name} (デバイスの次回ウェイク時に配送)",
            }

        return {
            "success": True,
            "result": f"デバイスコマンド実行完了: {agent_id}/{tool_name} -> {json.dumps(result, ensure_ascii=False)}",
        }

    async def fetch_acceptance_audio(self) -> str | None:
        """
        Fetch a pre-generated acceptance audio URL from the voice service stock.
        Returns the audio URL on success, None on failure.
        Used when Brain detects a task has been accepted and wants to play audio.
        """
        try:
            async with self._session.get(
                f"{self.voice_url}/api/voice/acceptance/random",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    audio_url = data.get("audio_url")
                    logger.info(f"Fetched acceptance audio: {audio_url}")
                    return audio_url
                else:
                    logger.warning(f"Acceptance audio fetch failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Acceptance audio fetch error: {e}")
        return None

    async def _handle_get_zone_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed zone status from WorldModel."""
        zone_id = args.get("zone_id", "")
        zone = self.world_model.get_zone(zone_id)

        if zone is None:
            return {"success": False, "error": f"ゾーン '{zone_id}' が見つかりません"}

        # Build status string
        display_name = zone.metadata.display_name
        if display_name and display_name != zone_id:
            lines = [f"ゾーン: {display_name} ({zone_id})"]
        else:
            lines = [f"ゾーン: {zone_id}"]

        if zone.occupancy.person_count > 0:
            lines.append(f"在室: {zone.occupancy.person_count}名 ({zone.occupancy.activity_summary})")
        else:
            lines.append("在室: 無人")

        env = zone.environment
        if env.temperature is not None:
            lines.append(f"気温: {env.temperature:.1f}℃ ({env.thermal_comfort})")
        if env.humidity is not None:
            lines.append(f"湿度: {env.humidity:.0f}%")
        if env.co2 is not None:
            lines.append(f"CO2: {env.co2}ppm{'（換気必要）' if env.is_stuffy else ''}")
        if env.illuminance is not None:
            lines.append(f"照度: {env.illuminance:.0f}lux")
        if env.soil_moisture is not None:
            lines.append(f"土壌水分: {env.soil_moisture:.1f}%")
        if zone.occupancy.motion_event_count_5min > 0:
            lines.append(f"動体検知: 直近5分で{zone.occupancy.motion_event_count_5min}回")
        if zone.occupancy.presence_state is not None:
            dur_min = int(zone.occupancy.presence_duration_sec / 60)
            state_str = "在室検知中" if zone.occupancy.presence_state else "不在"
            lines.append(f"在室センサー: {state_str} ({dur_min}分間)")
        for dev_id, door_info in zone.occupancy.door_states.items():
            door_label = self.world_model.get_device_label(dev_id) or dev_id
            dur_min = int(door_info["duration_sec"] / 60)
            state_str = "開放中" if door_info["open"] else "閉鎖中"
            lines.append(f"ドア({door_label}): {state_str} ({dur_min}分間)")

        if zone.devices:
            for dev_id, dev in zone.devices.items():
                label = self.world_model.get_device_label(dev_id)
                if label:
                    lines.append(f"デバイス {label}({dev_id}): {dev.power_state}")
                else:
                    lines.append(f"デバイス {dev.device_type}({dev_id}): {dev.power_state}")

        # Spatial metadata
        meta = zone.metadata
        if meta.area_m2 > 0:
            lines.append(f"面積: {meta.area_m2:.1f}㎡")
        if meta.adjacent_zones:
            adj_names = []
            for adj_id in meta.adjacent_zones:
                adj_zone = self.world_model.get_zone(adj_id)
                if adj_zone and adj_zone.metadata.display_name and adj_zone.metadata.display_name != adj_id:
                    adj_names.append(f"{adj_zone.metadata.display_name} ({adj_id})")
                else:
                    adj_names.append(adj_id)
            lines.append(f"隣接ゾーン: {', '.join(adj_names)}")

        # Detected persons with floor coordinates
        persons_with_pos = [p for p in zone.spatial.persons if p.floor_position_m]
        if persons_with_pos:
            pos_strs = [f"({p.floor_position_m[0]:.1f}m, {p.floor_position_m[1]:.1f}m)" for p in persons_with_pos]
            lines.append(f"検出位置: {', '.join(pos_strs)}")

        return {"success": True, "result": "\n".join(lines)}

    async def _handle_get_active_tasks(self) -> Dict[str, Any]:
        """Get active tasks from DashboardClient."""
        tasks = await self.dashboard.get_active_tasks()
        if not tasks:
            return {"success": True, "result": "アクティブなタスクはありません"}

        summaries = []
        for t in tasks[:10]:  # Limit to 10
            title = t.get("title", "")
            completed = t.get("is_completed", False)
            zone = t.get("zone", "")
            task_type = t.get("task_type", [])
            status_str = "完了" if completed else "対応中"
            zone_str = f", zone: {zone}" if zone else ""
            type_str = f", type: {','.join(task_type)}" if task_type else ""
            summaries.append(f"- {title} ({status_str}{zone_str}{type_str})")

        return {
            "success": True,
            "result": f"アクティブなタスク ({len(tasks)}件):\n" + "\n".join(summaries),
        }

    async def _handle_get_device_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get device network status from DeviceRegistry."""
        if not self.device_registry:
            return {"success": False, "error": "DeviceRegistry が初期化されていません"}

        zone_id = args.get("zone_id")
        tree = self.device_registry.get_device_tree(zone_id=zone_id)
        return {"success": True, "result": tree}

    async def _handle_check_inventory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get inventory status from InventoryTracker."""
        if not self.inventory_tracker:
            return {"success": False, "error": "InventoryTracker が初期化されていません"}

        zone = args.get("zone")
        items = self.inventory_tracker.get_inventory_status(zone)
        if not items:
            return {"success": True, "result": "在庫追跡対象の棚はありません"}

        lines = []
        for item in items:
            status_icon = "⚠️" if item["status"] == "low" else "✅"
            lines.append(
                f"{status_icon} {item['item_name']} [{item['zone']}]: "
                f"残量{item['quantity']}個 (閾値: {item['min_threshold']})"
            )
        return {"success": True, "result": "\n".join(lines)}

    async def _handle_add_shopping_item(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add item to shopping list via Dashboard API."""
        result = await self.dashboard.add_shopping_item(
            name=args.get("name", ""),
            category=args.get("category"),
            quantity=args.get("quantity", 1),
            store=args.get("store"),
            price=args.get("price"),
            notes=args.get("notes"),
        )
        if result:
            return {
                "success": True,
                "result": f"買い物リストに追加: {args.get('name')} x{args.get('quantity', 1)}",
            }
        return {"success": False, "error": "買い物リストへの追加に失敗しました"}

    async def _handle_calibrate_shelf(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shelf sensor calibration via CalibrationManager + MCP."""
        if not self.calibration_manager:
            return {"success": False, "error": "CalibrationManager が初期化されていません"}

        device_id = args.get("device_id", "")
        step = args.get("step", "")

        # Validate step ordering
        is_valid, reason = self.calibration_manager.validate_step(device_id, step)
        if not is_valid:
            return {"success": False, "error": reason}

        if step == "tare":
            # Start/restart session and send tare command via MCP
            self.calibration_manager.start_or_get(device_id)
            result = await self.mcp.call_tool(device_id, "tare", {})
            if isinstance(result, dict) and result.get("status") == "ok":
                self.calibration_manager.record_tare_done(device_id, result)
                return {
                    "success": True,
                    "result": f"棚センサ {device_id} のゼロ点設定完了。次に既知重量を載せて step='set_known_weight' を実行してください。",
                }
            return {"success": False, "error": f"Tare失敗: {result}"}

        elif step == "set_known_weight":
            known_weight_g = args.get("known_weight_g")
            if not known_weight_g or known_weight_g <= 0:
                return {"success": False, "error": "known_weight_g は正の数を指定してください"}
            result = await self.mcp.call_tool(
                device_id, "calibrate", {"known_weight_g": known_weight_g}
            )
            if isinstance(result, dict) and result.get("status") == "ok":
                self.calibration_manager.record_calibrate_done(device_id, result)
                self.calibration_manager.finish(device_id)
                scale = result.get("scale", "?")
                return {
                    "success": True,
                    "result": f"棚センサ {device_id} のキャリブレーション完了 (scale={scale})",
                }
            return {"success": False, "error": f"キャリブレーション失敗: {result}"}

    async def _handle_trigger_display_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger a cross-dashboard coordination event via Dashboard API."""
        event_type = args.get("event_type", "avatar_traversal")
        animation = args.get("animation", "run")
        speed = args.get("speed", "normal")

        # Parse display_ids from comma-separated string
        display_ids_str = args.get("display_ids")
        display_ids = None
        if display_ids_str:
            display_ids = [d.strip() for d in display_ids_str.split(",") if d.strip()]

        if event_type == "avatar_traversal":
            try:
                async with self._session.post(
                    f"{self.dashboard_api_url}/coordination/avatar-traversal",
                    json={
                        "display_ids": display_ids,
                        "animation": animation,
                        "speed": speed,
                    },
                    headers=self._service_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        count = len(data.get("sequence", []))
                        return {
                            "success": True,
                            "result": f"アバター横断アニメーションをトリガーしました ({count}台のディスプレイ)",
                        }
                    else:
                        text = await resp.text()
                        return {"success": False, "error": f"Coordination API エラー: {resp.status} {text}"}
            except Exception as e:
                return {"success": False, "error": f"Display event trigger failed: {e}"}
        else:
            return {"success": False, "error": f"未知のイベント種別: {event_type}"}
