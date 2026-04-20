import ZoneOverviewSection from './analytics/ZoneOverviewSection';
import TimeSeriesSection from './analytics/TimeSeriesSection';
import LLMTimelineSection from './analytics/LLMTimelineSection';
import HeatmapSection from './analytics/HeatmapSection';
import LatestReadingsSection from './analytics/LatestReadingsSection';
import LLMActivitySection from './analytics/LLMActivitySection';

export default function AnalyticsPage() {
  return (
    <main className="max-w-6xl mx-auto px-6 py-8">
      <section className="mb-8">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Zone Overview</h2>
        <p className="text-[var(--gray-600)] mb-4">Current sensor readings per zone.</p>
        <ZoneOverviewSection />
      </section>

      <section className="mb-8">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Sensor Time Series</h2>
        <p className="text-[var(--gray-600)] mb-4">Historical sensor data with configurable aggregation.</p>
        <TimeSeriesSection />
      </section>

      <section className="mb-8">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Brain Activity Timeline</h2>
        <p className="text-[var(--gray-600)] mb-4">LLM cognitive cycles and tool usage over time.</p>
        <LLMTimelineSection />
      </section>

      <section className="mb-8">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Occupancy Heatmap</h2>
        <p className="text-[var(--gray-600)] mb-4">Spatial occupancy density over time.</p>
        <HeatmapSection />
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section>
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Sensor Data</h2>
          <p className="text-[var(--gray-600)] mb-4">Latest individual readings.</p>
          <LatestReadingsSection />
        </section>

        <section>
          <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">Brain Activity</h2>
          <p className="text-[var(--gray-600)] mb-4">LLM cognitive cycles and event feed.</p>
          <LLMActivitySection />
        </section>
      </div>
    </main>
  );
}
