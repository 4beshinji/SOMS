# ADR: Spatial Map Service

## Status
Accepted

## Context
SOMS manages zones as string IDs with no spatial metadata. Phase 1 multi-zone expansion requires zone correlation analysis, which needs spatial relationship knowledge. Additionally, the Perception service computes YOLO detection data (bounding boxes, center coordinates) but discards all spatial data after aggregation, publishing only summary counts.

## Decision

### Three-Phase Implementation

**Phase 1 — Spatial Config + Perception Publish + WorldModel Extension**
- `config/spatial.yaml`: zone polygons, device positions, camera positions
- `SpatialDetection`, `ZoneSpatialData`, `ZoneMetadata` dataclasses added to WorldModel
- Perception monitors publish to `office/{zone}/spatial/{camera_id}` with bbox/center data
- WorldModel accumulates pixel-based heatmap grid per zone, resets hourly
- LLM context enriched with person distribution and adjacent zone occupancy

**Phase 2 — Event Store + Dashboard Backend + Frontend FloorPlan**
- `events.spatial_snapshots` and `events.spatial_heatmap_hourly` tables
- EventWriter buffers spatial snapshots (10s dedup per zone)
- Repository pattern: `SpatialDataRepository` ABC + `PgSpatialRepository`
- REST API: `/sensors/spatial/config`, `/live`, `/heatmap`
- SVG-based FloorPlanView with zone polygons, device markers, tab navigation

**Phase 3 — Heatmap Aggregation + Real-time Display**
- HourlyAggregator rolls spatial_snapshots into spatial_heatmap_hourly
- 90-day retention for spatial snapshots
- HeatmapLayer (SVG rects with clip-path), PersonLayer (animated dots), FloorPlanControls

### Privacy
No raw images, faces, or pose keypoints are published or stored. Only bounding box centers, class names, and confidence scores flow through the spatial pipeline.

### MQTT Topic
```
office/{zone}/spatial/{camera_id}
```
Payload: `{zone, camera_id, timestamp, image_size, persons: [{center_px, bbox_px, confidence}], objects: [{class_name, center_px, bbox_px, confidence}]}`

## Consequences
- Enables zone correlation analysis for multi-zone LLM decisions
- Dashboard gains floor plan visualization with real-time occupancy
- Event store captures spatial patterns for historical analysis
- ~100-150 chars additional LLM context per active zone
- Spatial snapshots add ~1 row/10s/zone to PostgreSQL (managed by 90d retention)
