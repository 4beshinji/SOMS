/**
 * Browser MQTT client for cross-dashboard coordination.
 * Connects via WebSocket through nginx proxy (/mqtt → mosquitto:9001).
 */
import mqtt from 'mqtt';

export type MessageHandler = (topic: string, payload: unknown) => void;

export class MqttClient {
  private client: mqtt.MqttClient | null = null;
  private handlers = new Map<string, Set<MessageHandler>>();
  private displayId: string;

  constructor(displayId: string) {
    this.displayId = displayId;
  }

  async connect(): Promise<void> {
    if (this.client) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${window.location.host}/mqtt`;

    this.client = mqtt.connect(url, {
      username: 'soms',
      password: 'soms_dev_mqtt',
      clientId: `display_${this.displayId}_${Date.now()}`,
      clean: true,
      reconnectPeriod: 5000,
      connectTimeout: 10000,
    });

    this.client.on('connect', () => {
      console.log(`[MQTT] Connected as display ${this.displayId}`);
      // Subscribe to display-specific and coordination topics
      this.client?.subscribe([
        `soms/display/${this.displayId}/command`,
        'soms/display/all/command',
        'soms/coordination/+/sequence',
      ]);
    });

    this.client.on('message', (topic: string, message: Buffer) => {
      let payload: unknown;
      try {
        payload = JSON.parse(message.toString());
      } catch {
        payload = message.toString();
      }

      // Dispatch to all matching handlers
      for (const [pattern, handlerSet] of this.handlers) {
        if (this.topicMatches(pattern, topic)) {
          for (const handler of handlerSet) {
            handler(topic, payload);
          }
        }
      }
    });

    this.client.on('error', (err) => {
      console.warn('[MQTT] Error:', err.message);
    });
  }

  disconnect(): void {
    this.client?.end(true);
    this.client = null;
  }

  subscribe(pattern: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(pattern)) {
      this.handlers.set(pattern, new Set());
    }
    this.handlers.get(pattern)!.add(handler);

    return () => {
      this.handlers.get(pattern)?.delete(handler);
    };
  }

  publish(topic: string, payload: unknown): void {
    if (!this.client?.connected) return;
    this.client.publish(topic, JSON.stringify(payload));
  }

  private topicMatches(pattern: string, topic: string): boolean {
    const patParts = pattern.split('/');
    const topParts = topic.split('/');

    for (let i = 0; i < patParts.length; i++) {
      if (patParts[i] === '#') return true;
      if (patParts[i] === '+') continue;
      if (i >= topParts.length || patParts[i] !== topParts[i]) return false;
    }
    return patParts.length === topParts.length;
  }
}
