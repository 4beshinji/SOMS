import FloorPlanView from '../components/FloorPlan/FloorPlanView';

export default function FloorPlanPage() {
  return (
    <div className="p-6">
      <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-6">Floor Plan</h2>
      <FloorPlanView />
    </div>
  );
}
