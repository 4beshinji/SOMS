"""Tests for WorldModel VLM integration — topic parsing, event creation, LLM context."""
import time
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from world_model.world_model import WorldModel
from world_model.data_classes import Event


class TestUpdateVLM:
    def setup_method(self):
        self.wm = WorldModel()

    def test_vlm_topic_parsed(self):
        """office/{zone}/vlm/{type} should route to _update_vlm."""
        result = self.wm._parse_topic("office/kitchen/vlm/scene")
        assert result is not None
        assert result["zone"] == "kitchen"
        assert result["device_type"] == "vlm"

    def test_vlm_update_creates_event(self):
        payload = {
            "analysis_type": "scene",
            "trigger": "periodic",
            "content": "キッチンに2人がいて料理をしています",
            "model": "qwen3-vl:8b",
            "latency_sec": 5.2,
            "timestamp": time.time(),
        }
        self.wm.update_from_mqtt("office/kitchen/vlm/scene", payload)

        zone = self.wm.zones.get("kitchen")
        assert zone is not None
        assert len(zone.events) == 1
        event = zone.events[0]
        assert event.event_type == "vlm_analysis"
        assert event.severity == "info"
        assert event.data["analysis_type"] == "scene"
        assert "キッチン" in event.data["content"]

    def test_vlm_content_truncated(self):
        long_content = "A" * 500
        payload = {"analysis_type": "scene", "content": long_content}
        self.wm.update_from_mqtt("office/kitchen/vlm/scene", payload)
        event = self.wm.zones["kitchen"].events[0]
        assert len(event.data["content"]) <= 200

    def test_vlm_multiple_types(self):
        for atype in ["scene", "occupancy_change", "fall_candidate"]:
            payload = {"analysis_type": atype, "content": f"Analysis: {atype}"}
            self.wm.update_from_mqtt(f"office/kitchen/vlm/{atype}", payload)
        assert len(self.wm.zones["kitchen"].events) == 3


class TestEventDescription:
    def test_vlm_analysis_description(self):
        event = Event(
            timestamp=time.time(),
            event_type="vlm_analysis",
            severity="info",
            data={"analysis_type": "scene", "content": "キッチンに2人がいます"},
        )
        desc = event.description
        assert "VLM分析" in desc
        assert "scene" in desc
        assert "キッチン" in desc

    def test_vlm_analysis_long_content_truncated(self):
        event = Event(
            timestamp=time.time(),
            event_type="vlm_analysis",
            severity="info",
            data={"analysis_type": "fall_candidate", "content": "X" * 200},
        )
        desc = event.description
        assert len(desc) < 200  # content[:100] + prefix

    def test_vlm_analysis_empty_content(self):
        event = Event(
            timestamp=time.time(),
            event_type="vlm_analysis",
            severity="info",
            data={"analysis_type": "scene"},
        )
        desc = event.description
        assert "VLM分析(scene)" in desc


class TestLLMContextVLM:
    def test_recent_vlm_in_context(self):
        wm = WorldModel()
        payload = {
            "analysis_type": "scene",
            "trigger": "periodic",
            "content": "会議室に3人が会議中です",
        }
        wm.update_from_mqtt("office/meeting_room/vlm/scene", payload)
        context = wm.get_llm_context()
        assert "VLM分析" in context
        assert "会議室に3人" in context

    def test_old_vlm_not_in_context(self):
        wm = WorldModel()
        from world_model.data_classes import ZoneState
        wm.zones["kitchen"] = ZoneState(zone_id="kitchen")
        zone = wm.zones["kitchen"]
        event = Event(
            timestamp=time.time() - 700,  # > 600s ago
            event_type="vlm_analysis",
            severity="info",
            data={"analysis_type": "scene", "content": "古い分析結果"},
        )
        zone.events.append(event)

        context = wm.get_llm_context()
        assert "VLM分析: 古い分析結果" not in context

    def test_no_vlm_no_extra_line(self):
        wm = WorldModel()
        wm.update_from_mqtt(
            "office/kitchen/sensor/env_01/temperature",
            {"value": 22.5},
        )
        context = wm.get_llm_context()
        assert "VLM分析" not in context


class TestMQTTRouting:
    def test_vlm_routes_correctly(self):
        wm = WorldModel()
        payload = {
            "analysis_type": "fall_candidate",
            "content": "転倒ではなく、しゃがんでいます",
            "trigger": "event",
        }
        wm.update_from_mqtt("office/entrance/vlm/fall_candidate", payload)

        zone = wm.zones.get("entrance")
        assert zone is not None
        assert len(zone.events) == 1
        assert zone.events[0].data["analysis_type"] == "fall_candidate"

    def test_vlm_does_not_interfere_with_anomaly(self):
        wm = WorldModel()
        wm.update_from_mqtt(
            "office/kitchen/vlm/scene",
            {"content": "VLM result"},
        )
        wm.update_from_mqtt(
            "office/kitchen/anomaly/temperature",
            {"score": 4.5, "predicted": 22.0, "actual": 28.0, "severity": "warning"},
        )
        zone = wm.zones["kitchen"]
        assert len(zone.events) == 2
        types = {e.event_type for e in zone.events}
        assert "vlm_analysis" in types
        assert "anomaly_detected" in types
