/**
 * Handles cross-dashboard coordination events received via MQTT.
 * Manages avatar traversal state machine for this display.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useMqttSubscription } from './useMqtt';
import { useDisplayIdentity } from './useDisplayIdentity';

export type TraversalPhase = 'idle' | 'entering' | 'present' | 'exiting' | 'hidden';

export interface TraversalState {
  phase: TraversalPhase;
  enterEdge: 'left' | 'right';
  exitEdge: 'left' | 'right';
  /** 0..1 progress within the current phase */
  progress: number;
  animation: string;
}

interface SequenceEntry {
  display_id: string;
  order: number;
  enter_ms: number;
  exit_ms: number;
  enter_edge: string;
  exit_edge: string;
}

interface CoordinationEvent {
  event_type: string;
  event_id: string;
  animation: string;
  sequence: SequenceEntry[];
  start_at_epoch_ms: number;
}

const IDLE_STATE: TraversalState = {
  phase: 'idle',
  enterEdge: 'left',
  exitEdge: 'right',
  progress: 0,
  animation: 'run',
};

export function useCoordination(): TraversalState {
  const { displayId } = useDisplayIdentity();
  const [state, setState] = useState<TraversalState>(IDLE_STATE);
  const rafRef = useRef<number>();
  const eventRef = useRef<{ entry: SequenceEntry; startAt: number; animation: string } | null>(null);

  // Animation loop
  useEffect(() => {
    const tick = () => {
      const ev = eventRef.current;
      if (!ev) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const now = Date.now();
      const elapsed = now - ev.startAt;
      const { enter_ms, exit_ms, enter_edge, exit_edge } = ev.entry;
      const duration = exit_ms - enter_ms;
      const enterDuration = duration * 0.2; // 20% entering
      const exitDuration = duration * 0.2;  // 20% exiting
      const presentStart = enter_ms + enterDuration;
      const exitStart = exit_ms - exitDuration;

      if (elapsed < enter_ms) {
        // Before this display's turn — hidden
        setState({ phase: 'hidden', enterEdge: enter_edge as 'left' | 'right', exitEdge: exit_edge as 'left' | 'right', progress: 0, animation: ev.animation });
      } else if (elapsed < presentStart) {
        // Entering
        const p = (elapsed - enter_ms) / enterDuration;
        setState({ phase: 'entering', enterEdge: enter_edge as 'left' | 'right', exitEdge: exit_edge as 'left' | 'right', progress: Math.min(p, 1), animation: ev.animation });
      } else if (elapsed < exitStart) {
        // Present
        const p = (elapsed - presentStart) / (exitStart - presentStart);
        setState({ phase: 'present', enterEdge: enter_edge as 'left' | 'right', exitEdge: exit_edge as 'left' | 'right', progress: Math.min(p, 1), animation: ev.animation });
      } else if (elapsed < exit_ms) {
        // Exiting
        const p = (elapsed - exitStart) / exitDuration;
        setState({ phase: 'exiting', enterEdge: enter_edge as 'left' | 'right', exitEdge: exit_edge as 'left' | 'right', progress: Math.min(p, 1), animation: ev.animation });
      } else {
        // Done
        eventRef.current = null;
        setState(IDLE_STATE);
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // MQTT handler
  const handleCoordination = useCallback(
    (_topic: string, payload: unknown) => {
      if (!displayId) return;
      const event = payload as CoordinationEvent;
      if (event.event_type !== 'avatar_traversal') return;

      const myEntry = event.sequence.find((e) => e.display_id === displayId);
      if (!myEntry) return;

      eventRef.current = {
        entry: myEntry,
        startAt: event.start_at_epoch_ms,
        animation: event.animation,
      };
      setState({ phase: 'hidden', enterEdge: 'left', exitEdge: 'right', progress: 0, animation: event.animation });
    },
    [displayId],
  );

  useMqttSubscription(
    displayId ? 'soms/coordination/+/sequence' : null,
    handleCoordination,
  );

  return state;
}
