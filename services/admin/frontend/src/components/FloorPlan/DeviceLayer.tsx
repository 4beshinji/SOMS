import { useState, useCallback, useRef, useEffect } from 'react';
import type { DevicePosition, CameraConfig } from '@soms/types';

interface DeviceLayerProps {
  devices: Record<string, DevicePosition>;
  cameras: Record<string, CameraConfig>;
  sensorData?: Record<string, Record<string, number>>;
  editMode?: boolean;
  dbDeviceIds?: Set<string>;
  selectedDevice?: string | null;
  onDeviceSelect?: (deviceId: string | null) => void;
  onDeviceDragEnd?: (deviceId: string, x: number, y: number) => void;
  onDeviceDelete?: (deviceId: string) => void;
  svgRef?: React.RefObject<SVGSVGElement | null>;
}

function tempColor(temp: number | undefined): string {
  if (temp === undefined) return '#6b7280';
  if (temp < 18) return '#3b82f6';
  if (temp > 26) return '#ef4444';
  return '#10b981';
}

function co2Color(co2: number | undefined): string {
  if (co2 === undefined) return '#6b7280';
  if (co2 > 1000) return '#ef4444';
  if (co2 > 800) return '#f59e0b';
  return '#10b981';
}

function formatValue(channel: string, value: number): string {
  switch (channel) {
    case 'temperature': return `${value.toFixed(1)}°`;
    case 'humidity': return `${value.toFixed(0)}%`;
    case 'co2': return `${value.toFixed(0)}`;
    case 'pressure': return `${value.toFixed(0)}`;
    default: return value.toFixed(1);
  }
}

export default function DeviceLayer({
  devices,
  cameras,
  sensorData,
  editMode = false,
  dbDeviceIds,
  selectedDevice,
  onDeviceSelect,
  onDeviceDragEnd,
  onDeviceDelete,
  svgRef,
}: DeviceLayerProps) {
  const [dragging, setDragging] = useState<{ deviceId: string; x: number; y: number } | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);

  const svgPointFromEvent = useCallback(
    (e: MouseEvent | React.MouseEvent) => {
      const svg = svgRef?.current;
      if (!svg) return null;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      return pt.matrixTransform(svg.getScreenCTM()?.inverse());
    },
    [svgRef],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent, deviceId: string, x: number, y: number) => {
      if (!editMode || !dbDeviceIds?.has(deviceId)) return;
      e.stopPropagation();
      e.preventDefault();
      dragStartRef.current = { x: e.clientX, y: e.clientY };
      setDragging({ deviceId, x, y });
    },
    [editMode, dbDeviceIds],
  );

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const pt = svgPointFromEvent(e);
      if (!pt) return;
      setDragging(prev => prev ? { ...prev, x: pt.x, y: pt.y } : null);
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (!dragging) return;
      // Only trigger drag if mouse moved significantly
      const start = dragStartRef.current;
      const dist = start ? Math.hypot(e.clientX - start.x, e.clientY - start.y) : 0;
      if (dist > 3) {
        const pt = svgPointFromEvent(e);
        if (pt) {
          onDeviceDragEnd?.(dragging.deviceId, pt.x, pt.y);
        }
      }
      setDragging(null);
      dragStartRef.current = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, svgPointFromEvent, onDeviceDragEnd]);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, deviceId: string) => {
      if (!editMode || !dbDeviceIds?.has(deviceId)) return;
      e.preventDefault();
      e.stopPropagation();
      onDeviceDelete?.(deviceId);
    },
    [editMode, dbDeviceIds, onDeviceDelete],
  );

  const handleClick = useCallback(
    (e: React.MouseEvent, deviceId: string) => {
      e.stopPropagation();
      if (!editMode) {
        onDeviceSelect?.(deviceId);
      }
    },
    [editMode, onDeviceSelect],
  );

  return (
    <g className="device-layer">
      {/* Sensor devices */}
      {Object.entries(devices).map(([deviceId, dev]) => {
        const isDragging = dragging?.deviceId === deviceId;
        const x = isDragging ? dragging.x : dev.position[0];
        const y = isDragging ? dragging.y : dev.position[1];
        const data = sensorData?.[deviceId] || {};
        const temp = data['temperature'];
        const co2 = data['co2'];
        const color = temp !== undefined ? tempColor(temp) : co2Color(co2);
        const isSelected = selectedDevice === deviceId;
        const isDraggable = editMode && dbDeviceIds?.has(deviceId);

        // Build tooltip values
        const valueLines = Object.entries(data).slice(0, 3);

        return (
          <g
            key={deviceId}
            role="button"
            aria-label={`Device ${deviceId}${data['temperature'] !== undefined ? `, temperature ${data['temperature'].toFixed(1)}°C` : ''}`}
            style={{ cursor: editMode ? (isDraggable ? 'grab' : 'default') : 'pointer' }}
            onMouseDown={(e) => handleMouseDown(e, deviceId, x, y)}
            onContextMenu={(e) => handleContextMenu(e, deviceId)}
            onClick={(e) => handleClick(e, deviceId)}
          >
            {/* Selection highlight ring */}
            {isSelected && (
              <circle
                cx={x}
                cy={y}
                r={0.45}
                fill="none"
                stroke="#3b82f6"
                strokeWidth={0.06}
                strokeDasharray="0.1 0.06"
              >
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to="0.32"
                  dur="1s"
                  repeatCount="indefinite"
                />
              </circle>
            )}

            {/* Edit mode indicator ring */}
            {isDraggable && (
              <circle
                cx={x}
                cy={y}
                r={0.38}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={0.04}
                strokeDasharray="0.08 0.08"
                opacity={0.6}
              />
            )}

            {/* Main circle */}
            <circle
              cx={x}
              cy={y}
              r={0.3}
              fill={color}
              opacity={isDragging ? 0.5 : 0.8}
              stroke="white"
              strokeWidth={0.05}
            />

            {/* Device label */}
            <text
              x={x}
              y={y + 0.55}
              textAnchor="middle"
              fontSize="0.28"
              fill="#374151"
              style={{ pointerEvents: 'none' }}
            >
              {deviceId}
            </text>

            {/* Primary value inside circle */}
            {temp !== undefined && (
              <text
                x={x}
                y={y + 0.08}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="0.22"
                fill="white"
                fontWeight="bold"
                style={{ pointerEvents: 'none' }}
              >
                {temp.toFixed(1)}
              </text>
            )}

            {/* Extra sensor values below label */}
            {valueLines.length > 0 && temp === undefined && (
              <text
                x={x}
                y={y + 0.08}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="0.18"
                fill="white"
                fontWeight="bold"
                style={{ pointerEvents: 'none' }}
              >
                {formatValue(valueLines[0][0], valueLines[0][1])}
              </text>
            )}
          </g>
        );
      })}

      {/* Cameras */}
      {Object.entries(cameras).map(([camId, cam]) => {
        const [x, y] = cam.position;
        const isSelected = selectedDevice === camId;
        return (
          <g
            key={camId}
            role="button"
            aria-label={`Camera ${camId}`}
            style={{ cursor: editMode ? 'default' : 'pointer' }}
            onClick={(e) => handleClick(e, camId)}
          >
            {isSelected && (
              <rect
                x={x - 0.32}
                y={y - 0.32}
                width={0.64}
                height={0.64}
                rx={0.08}
                fill="none"
                stroke="#3b82f6"
                strokeWidth={0.06}
                strokeDasharray="0.1 0.06"
              />
            )}
            <rect
              x={x - 0.2}
              y={y - 0.2}
              width={0.4}
              height={0.4}
              rx={0.05}
              fill="#7c3aed"
              opacity={0.8}
              stroke="white"
              strokeWidth={0.05}
            />
            <text
              x={x}
              y={y + 0.55}
              textAnchor="middle"
              fontSize="0.25"
              fill="#7c3aed"
              style={{ pointerEvents: 'none' }}
            >
              {camId}
            </text>
          </g>
        );
      })}
    </g>
  );
}
