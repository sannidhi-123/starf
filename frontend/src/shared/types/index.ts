export interface SystemHealth {
  status: string;
  environment: string;
  integration: string;
  latencyMs?: number;
}

export interface DatasetItem {
  id: string;
  name: string;
  filename?: string;
  rows: number;
  size_bytes?: number;
  size_formatted?: string;
}

export interface SampleFrame {
  timestamp: string;
  can_id: string;
  dlc: string;
  payload: string;
  raw_row?: Record<string, string>;
}

export interface DatasetDetails {
  id: string;
  name: string;
  filename: string;
  rows: number;
  size_bytes: number;
  size_formatted: string;
  columns: string[];
  sample_frames: SampleFrame[];
}

export interface CANFrameInput {
  timestamp: number;
  can_id: number | string;
  dlc: number;
  payload: string;
}

export interface DetectionRunRequest {
  dataset_id?: string;
  frames?: CANFrameInput[];
  rule_config?: Record<string, unknown>;
  model_id?: string;
  include_frame_evaluations?: boolean;
}

export interface AlertItem {
  id: number;
  run_id: string;
  created_at?: string;
  timestamp: number;
  can_id: number;
  can_id_hex: string;
  label: string;
  confidence: number;
  stage: string;
  severity_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  severity_score: number;
  rule_ids: string;
  reason: string;
}

export interface AlertSummary {
  total: number;
  by_label: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface DetectionResult {
  job_id: string;
  run_id: string;
  dataset_id?: string;
  status: string;
  total_frames: number;
  normal_count: number;
  alert_count: number;
  suspicious_count: number;
  matches: number;
  by_label: Record<string, number>;
  by_severity: Record<string, number>;
  rule_hits: Record<string, number>;
  execution_time_ms: number;
  summary: {
    total: number;
    by_label: Record<string, number>;
    by_severity: Record<string, number>;
  };
  alerts?: AlertItem[];
}

export interface MLModelRule {
  id: string;
  name: string;
  weight: number;
  level: string;
}

export interface MLModelSeverityLevel {
  level: string;
  range: string;
  description: string;
}

export interface MLModel {
  id: string;
  name: string;
  stage: string;
  type: string;
  version: string;
  status: 'active' | 'stub' | string;
  status_label: string;
  description: string;
  rules?: MLModelRule[];
  classes?: string[];
  features?: string[];
  matrix_rows?: number;
  severity_levels?: MLModelSeverityLevel[];
  metrics?: Record<string, string | number>;
}
