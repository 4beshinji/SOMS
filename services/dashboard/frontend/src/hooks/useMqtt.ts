/**
 * React hook for MQTT client lifecycle management.
 * Only connects when display identity is available.
 */
import { useEffect, useRef } from 'react';
import { MqttClient, type MessageHandler } from '../mqtt/MqttClient';
import { useDisplayIdentity } from './useDisplayIdentity';

let sharedClient: MqttClient | null = null;

export function useMqtt() {
  const { displayId } = useDisplayIdentity();
  const clientRef = useRef<MqttClient | null>(null);

  useEffect(() => {
    if (!displayId) return;

    // Reuse or create shared client
    if (!sharedClient || sharedClient !== clientRef.current) {
      sharedClient = new MqttClient(displayId);
      sharedClient.connect().catch(() => {});
    }
    clientRef.current = sharedClient;

    return () => {
      // Don't disconnect on unmount — shared across components
    };
  }, [displayId]);

  return clientRef.current;
}

export function useMqttSubscription(
  pattern: string | null,
  handler: MessageHandler,
) {
  const client = useMqtt();

  useEffect(() => {
    if (!client || !pattern) return;
    return client.subscribe(pattern, handler);
  }, [client, pattern, handler]);
}
