// Spatial Map types for floor plan visualization

export interface BuildingConfig {
  name: string;
  width_m: number;
  height_m: number;
  floor_plan_image: string | null;
}

export interface ZoneGeometry {
  display_name: string;
  polygon: number[][];
  area_m2: number;
  floor: number;
  adjacent_zones: string[];
  grid_cols: number;
  grid_rows: number;
}

export interface DevicePosition {
  zone: string;
  position: number[];
  type: string;
  channels: string[];
}

export interface CameraConfig {
  zone: string;
  position: number[];
  resolution: number[];
  fov_deg: number;
  orientation_deg: number;
}

export interface SpatialConfig {
  building: BuildingConfig;
  zones: Record<string, ZoneGeometry>;
  devices: Record<string, DevicePosition>;
  cameras: Record<string, CameraConfig>;
}

export interface SpatialDetection {
  class_name?: string;
  center_px: number[];
  bbox_px: number[];
  confidence: number;
}

export interface LiveSpatialData {
  zone: string;
  camera_id: string | null;
  timestamp: string | null;
  image_size: number[];
  persons: SpatialDetection[];
  objects: SpatialDetection[];
}

export interface HeatmapData {
  zone: string;
  period: string;
  grid_cols: number;
  grid_rows: number;
  cell_counts: number[][];
  person_count_avg: number;
  period_start: string | null;
  period_end: string | null;
}

export type FloorPlanLayer = 'zones' | 'devices' | 'heatmap' | 'persons' | 'objects';
