"""Tests for AnomalyMQTTClient — publish, subscribe, and message routing."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch, call

from scorer import AnomalyResult
from mqtt_client import AnomalyMQTTClient


@pytest.fixture
def mock_paho_client():
    """Provide a MagicMock standing in for paho.mqtt.client.Client."""
    mock_client_cls = MagicMock()
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance
    return mock_client_cls, mock_instance


@pytest.fixture
def mqtt_client(mock_paho_client):
    """Create an AnomalyMQTTClient with paho.mqtt.client.Client patched."""
    mock_cls, mock_instance = mock_paho_client
    with patch("mqtt_client.mqtt.Client", mock_cls):
        client = AnomalyMQTTClient()
    return client, mock_instance


@pytest.fixture
def mqtt_client_with_callback(mock_paho_client):
    """Create an AnomalyMQTTClient with a sensor message callback."""
    mock_cls, mock_instance = mock_paho_client
    callback = MagicMock()
    with patch("mqtt_client.mqtt.Client", mock_cls):
        client = AnomalyMQTTClient(on_sensor_message=callback)
    return client, mock_instance, callback


def _make_result(**overrides):
    defaults = dict(
        zone="zone_01",
        channel="temperature",
        score=4.2,
        predicted=22.5,
        actual=28.1,
        severity="warning",
        source="batch",
    )
    defaults.update(overrides)
    return AnomalyResult(**defaults)


class TestPublishAnomaly:
    def test_publish_sends_correct_topic_and_payload(self, mqtt_client):
        """publish_anomaly() should call paho publish with the right topic and JSON payload."""
        client, mock_paho = mqtt_client
        result = _make_result(zone="meeting_room", channel="co2", score=5.1,
                              predicted=400.0, actual=1200.0, severity="critical",
                              source="realtime")

        client.publish_anomaly(result)

        mock_paho.publish.assert_called_once()
        topic, payload_str, *_ = mock_paho.publish.call_args.args
        assert topic == "office/meeting_room/anomaly/co2"
        payload = json.loads(payload_str)
        assert payload["score"] == 5.1
        assert payload["predicted"] == 400.0
        assert payload["actual"] == 1200.0
        assert payload["severity"] == "critical"
        assert payload["source"] == "realtime"
        assert payload["channel"] == "co2"
        assert payload["zone"] == "meeting_room"
        assert "timestamp" in payload

    def test_publish_uses_qos_1(self, mqtt_client):
        """publish_anomaly() should publish with QoS 1."""
        client, mock_paho = mqtt_client
        client.publish_anomaly(_make_result())

        _, kwargs = mock_paho.publish.call_args
        # qos may be passed as positional arg (3rd) or keyword
        call_args = mock_paho.publish.call_args
        # publish(topic, payload, qos=1)
        if len(call_args.args) >= 3:
            assert call_args.args[2] == 1
        else:
            assert call_args.kwargs.get("qos") == 1


class TestOnConnect:
    def test_successful_connect_sets_connected_flag(self, mqtt_client):
        """_on_connect with rc=0 should set connected to True."""
        client, mock_paho = mqtt_client
        assert client.connected is False

        client._on_connect(mock_paho, None, None, 0)

        assert client.connected is True

    def test_successful_connect_subscribes_when_callback_present(self, mqtt_client_with_callback):
        """_on_connect should subscribe to sensor topics when on_sensor_message is set."""
        client, mock_paho, _ = mqtt_client_with_callback

        client._on_connect(mock_paho, None, None, 0)

        mock_paho.subscribe.assert_called_once_with("office/+/sensor/+/+", qos=0)

    def test_successful_connect_does_not_subscribe_without_callback(self, mqtt_client):
        """_on_connect should NOT subscribe when no on_sensor_message callback."""
        client, mock_paho = mqtt_client

        client._on_connect(mock_paho, None, None, 0)

        mock_paho.subscribe.assert_not_called()

    def test_failed_connect_does_not_set_connected(self, mqtt_client):
        """_on_connect with non-zero rc should leave connected as False."""
        client, mock_paho = mqtt_client

        client._on_connect(mock_paho, None, None, 5)

        assert client.connected is False


class TestOnMessage:
    def test_valid_sensor_message_calls_callback(self, mqtt_client_with_callback):
        """_on_message should parse a sensor topic and invoke the callback with zone, channel, value."""
        client, mock_paho, callback = mqtt_client_with_callback

        msg = MagicMock()
        msg.topic = "office/zone_01/sensor/env_01/temperature"
        msg.payload = json.dumps({"value": 23.4}).encode()

        client._on_message(mock_paho, None, msg)

        callback.assert_called_once_with("zone_01", "temperature", 23.4)

    def test_non_sensor_topic_is_ignored(self, mqtt_client_with_callback):
        """_on_message should ignore topics that are not sensor readings."""
        client, mock_paho, callback = mqtt_client_with_callback

        msg = MagicMock()
        msg.topic = "office/zone_01/camera/cam_01/status"
        msg.payload = json.dumps({"value": 1}).encode()

        client._on_message(mock_paho, None, msg)

        callback.assert_not_called()

    def test_missing_value_key_is_ignored(self, mqtt_client_with_callback):
        """_on_message should not invoke callback when payload has no 'value' key."""
        client, mock_paho, callback = mqtt_client_with_callback

        msg = MagicMock()
        msg.topic = "office/zone_01/sensor/env_01/humidity"
        msg.payload = json.dumps({"status": "ok"}).encode()

        client._on_message(mock_paho, None, msg)

        callback.assert_not_called()

    def test_malformed_json_does_not_raise(self, mqtt_client_with_callback):
        """_on_message should silently handle unparseable payloads."""
        client, mock_paho, callback = mqtt_client_with_callback

        msg = MagicMock()
        msg.topic = "office/zone_01/sensor/env_01/temperature"
        msg.payload = b"not-json"

        # Should not raise
        client._on_message(mock_paho, None, msg)

        callback.assert_not_called()


class TestDisconnect:
    def test_on_disconnect_clears_connected_flag(self, mqtt_client):
        """_on_disconnect should set connected to False."""
        client, mock_paho = mqtt_client
        client._connected = True

        client._on_disconnect(mock_paho, None, None, 0)

        assert client.connected is False
