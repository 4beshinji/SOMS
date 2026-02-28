// ── Auth Types ───────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  username: string;
  display_name: string | null;
}

export interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (provider: 'slack' | 'github') => void;
  logout: () => void;
}

// ── Task Types ───────────────────────────────────────────────────────

export interface Task {
  id: number;
  title: string;
  description: string;
  location?: string;
  bounty_gold: number;
  bounty_xp: number;
  urgency: number;
  is_completed: boolean;
  announcement_audio_url?: string;
  announcement_text?: string;
  completion_audio_url?: string;
  completion_text?: string;
  created_at: string;
  completed_at?: string;
  task_type?: string[];
  assigned_to?: number;
  report_status?: string;
  completion_note?: string;
  zone?: string;
  reward_multiplier?: number;
  reward_adjusted_bounty?: number;
}

export interface TaskReport {
  status: string;
  note: string;
}

// ── System Stats ─────────────────────────────────────────────────────

export interface SystemStats {
  total_xp: number;
  tasks_completed: number;
  tasks_created: number;
  tasks_active: number;
  tasks_queued: number;
  tasks_completed_last_hour: number;
}

export interface SupplyStats {
  total_issued: number;
  total_burned: number;
  circulating: number;
}

export interface ZoneMultiplierInfo {
  zone: string;
  multiplier: number;
  device_count: number;
  avg_xp: number;
  devices: { device_id: string; xp: number; contribution: number }[];
}

// ── Wallet Types ─────────────────────────────────────────────────────

export interface Wallet {
  id: number;
  user_id: number;
  balance: number;
  created_at: string;
  updated_at: string;
}

export interface LedgerEntry {
  id: number;
  transaction_id: string;
  wallet_id: number;
  amount: number;
  balance_after: number;
  entry_type: 'DEBIT' | 'CREDIT';
  transaction_type: string;
  description: string | null;
  reference_id: string | null;
  counterparty_wallet_id: number | null;
  created_at: string;
}

export interface TransferFeeInfo {
  fee_rate: number;
  fee_amount: number;
  net_amount: number;
  min_transfer: number;
  below_minimum: boolean;
}

// ── Device / Stakes Types ────────────────────────────────────────────

export interface Device {
  id: number;
  device_id: string;
  owner_id: number;
  device_type: string;
  display_name: string | null;
  is_active: boolean;
  total_shares: number;
  available_shares: number;
  share_price: number;
  funding_open: boolean;
  power_mode: string;
  battery_pct: number | null;
  utility_score: number;
  xp: number;
  last_heartbeat_at: string | null;
}

export interface StakeResponse {
  id: number;
  device_id: number;
  user_id: number;
  shares: number;
  percentage: number;
  acquired_at: string;
}

export interface DeviceFundingResponse {
  device_id: string;
  total_shares: number;
  available_shares: number;
  share_price: number;
  funding_open: boolean;
  stakeholders: StakeResponse[];
  estimated_reward_per_hour: number;
}

export interface PortfolioEntry {
  device_id: string;
  device_type: string;
  shares: number;
  total_shares: number;
  percentage: number;
  estimated_reward_per_hour: number;
}

export interface PortfolioResponse {
  user_id: number;
  stakes: PortfolioEntry[];
  total_estimated_reward_per_hour: number;
}

export interface PoolListItem {
  id: number;
  title: string;
  goal_jpy: number;
  raised_jpy: number;
  status: string;
  progress_pct: number;
  created_at: string;
}

// ── Sensor Types ─────────────────────────────────────────────────────

export interface SensorReading {
  timestamp: string;
  zone: string;
  channel: string;
  value: number;
  device_id: string | null;
}

// ── Spatial Types ────────────────────────────────────────────────────

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

export type FloorPlanLayer = 'zones' | 'devices' | 'cameras' | 'heatmap' | 'persons' | 'objects';

// ── Device Position API Types ────────────────────────────────────────

export interface DevicePositionResponse {
  id: number;
  device_id: string;
  zone: string;
  x: number;
  y: number;
  device_type: string;
  channels: string[];
}

export interface CreateDevicePositionRequest {
  device_id: string;
  zone: string;
  x: number;
  y: number;
  device_type: string;
  channels: string[];
}

export interface UpdateDevicePositionRequest {
  x: number;
  y: number;
  zone?: string;
}
