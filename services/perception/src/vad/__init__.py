"""Video Anomaly Detection (VAD) — three-layer ensemble.

Layer 1: STG-NF   — Pose-based normalizing flow (skeleton sequence anomaly)
Layer 2: AED-MAE  — Frame-level masked autoencoder (scene reconstruction anomaly)
Layer 3: AI-VAD   — Attribute-based detector (velocity + appearance + pose features)
"""
