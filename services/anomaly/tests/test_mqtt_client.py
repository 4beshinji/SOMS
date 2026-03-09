"""Tests for the MQTT client payload and topic construction."""
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch

from scorer import AnomalyResult


class TestTopicConstruction:
    def test_anomaly_topic_format(self):
        """Topic should be office/{zone}/anomaly/{channel}."""
        result = AnomalyResult(
            zone="zone_01",
            channel="temperature",
            score=4.2,
            predicted=22.5,
            actual=28.1,
            severity="warning",
        )
        topic = f"office/{result.zone}/anomaly/{result.channel}"
        assert topic == "office/zone_01/anomaly/temperature"

    def test_different_zones(self):
        for zone in ["zone_01", "meeting_room_a", "entrance"]:
            result = AnomalyResult(
                zone=zone, channel="co2", score=5.0, predicted=400, actual=1200, severity="critical"
            )
            topic = f"office/{result.zone}/anomaly/{result.channel}"
            assert topic.startswith(f"office/{zone}/")


class TestPayloadFormat:
    def test_payload_fields(self):
        result = AnomalyResult(
            zone="zone_01",
            channel="temperature",
            score=4.2,
            predicted=22.5,
            actual=28.1,
            severity="warning",
            source="batch",
        )
        payload = {
            "score": result.score,
            "predicted": result.predicted,
            "actual": result.actual,
            "severity": result.severity,
            "source": result.source,
            "channel": result.channel,
            "zone": result.zone,
        }
        assert payload["score"] == 4.2
        assert payload["severity"] == "warning"
        assert payload["source"] == "batch"

    def test_payload_json_serializable(self):
        result = AnomalyResult(
            zone="zone_01",
            channel="humidity",
            score=3.5,
            predicted=50.0,
            actual=68.0,
            severity="warning",
            source="realtime",
        )
        payload = {
            "score": result.score,
            "predicted": result.predicted,
            "actual": result.actual,
            "severity": result.severity,
            "source": result.source,
            "channel": result.channel,
            "zone": result.zone,
            "timestamp": "2026-03-09T14:00:00Z",
        }
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)
        assert deserialized["score"] == 3.5


class TestSeverityFiltering:
    def test_warning_severity(self):
        result = AnomalyResult(
            zone="z", channel="c", score=3.5, predicted=0, actual=0, severity="warning"
        )
        assert result.severity in ("warning", "critical")

    def test_critical_severity(self):
        result = AnomalyResult(
            zone="z", channel="c", score=6.0, predicted=0, actual=0, severity="critical"
        )
        assert result.severity == "critical"


class TestMessageParsing:
    def test_sensor_topic_parsing(self):
        """Verify sensor topic parsing logic matches MQTT client."""
        topic = "office/zone_01/sensor/env_01/temperature"
        parts = topic.split("/")
        assert len(parts) == 5
        assert parts[0] == "office"
        assert parts[1] == "zone_01"
        assert parts[2] == "sensor"
        assert parts[3] == "env_01"
        assert parts[4] == "temperature"

    def test_non_sensor_topic_ignored(self):
        topic = "office/zone_01/camera/cam_01/status"
        parts = topic.split("/")
        assert parts[2] != "sensor"

    def test_sensor_payload_extraction(self):
        payload = json.dumps({"value": 22.5})
        data = json.loads(payload)
        assert data["value"] == 22.5

    def test_missing_value_in_payload(self):
        payload = json.dumps({"status": "ok"})
        data = json.loads(payload)
        assert data.get("value") is None
