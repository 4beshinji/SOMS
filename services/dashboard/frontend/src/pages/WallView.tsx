/**
 * WallView — washi/ink dashboard for wall-mounted office display.
 *
 * Replaces the generic SaaS look with a contemporary Japanese craft-brand
 * discipline (Niwaya / Banshokaku / Takenaka / Nippori Lamm refs).
 * Source of truth for the visual: design/dashboard-workshop.html.
 *
 * Mounted at `?view=wall` while we A/B with the existing Monitor.
 */
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Task, SensorReading } from '@soms/types';
import { useTaskManager } from '../hooks/useTaskManager';
import './WallView.css';

// ------------------------------------------------------------------
// data fetch
// ------------------------------------------------------------------
const fetchLatestSensors = async (): Promise<SensorReading[]> => {
  try {
    const res = await fetch('/api/sensors/latest');
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
};

// ------------------------------------------------------------------
// label maps — keep narrow; unknown zones fall through to raw value
// ------------------------------------------------------------------
const ZONE_LABELS: Record<string, { en: string; jp: string }> = {
  main:      { en: 'main',        jp: '主室' },
  main_west: { en: 'main · west', jp: '主室・西' },
  main_east: { en: 'main · east', jp: '主室・東' },
  lounge:    { en: 'lounge',      jp: '居間' },
  kitchen:   { en: 'kitchen',     jp: '給湯' },
  entry:     { en: 'entry',       jp: '玄関口' },
  work:      { en: 'work · n',    jp: '北・作業' },
  meeting:   { en: 'meeting',     jp: '会議室' },
};

const zoneLabel = (z?: string) =>
  z ? (ZONE_LABELS[z] ?? { en: z, jp: '' }) : { en: '—', jp: '' };

// urgency 0-4 → tag with the design's three categories
const tagFor = (urgency: number) => {
  if (urgency >= 4) return { label: '注意', alert: true,  routine: false };
  if (urgency >= 2) return { label: '依頼', alert: false, routine: false };
  return                { label: '日常', alert: false, routine: true  };
};

const pad = (n: number, w = 2) => String(n).padStart(w, '0');
const formatHHMM = (iso?: string) => {
  if (!iso) return '--:--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--';
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const formatId = (id: number) => `№ ${pad(id, 4)}`;

// 全角は ~1.0em、半角は ~0.5em。表示幅でカットする簡易関数。
const truncate = (s: string, max = 22) =>
  !s ? '' : s.length > max ? s.slice(0, max - 1) + '…' : s;

// ------------------------------------------------------------------
// component
// ------------------------------------------------------------------
export default function WallView() {
  const { visibleTasks } = useTaskManager();

  const sensorsQuery = useQuery({
    queryKey: ['sensors', 'latest'],
    queryFn: fetchLatestSensors,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  // clock — minute precision is enough for a wall display
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const sensors = sensorsQuery.data ?? [];
  const findChannel = (channel: string) =>
    sensors.find(s => s.channel === channel);

  const co2     = findChannel('co2');
  const temp    = findChannel('temperature');
  const humid   = findChannel('humidity');
  const pres    = findChannel('occupancy') ?? findChannel('person_count');

  const co2Val   = co2   ? Math.round(co2.value)        : null;
  const tempVal  = temp  ? temp.value.toFixed(1)        : null;
  const humidVal = humid ? Math.round(humid.value)      : null;
  const presVal  = pres  ? Math.round(pres.value)       : 0;

  const co2Flagged = co2Val !== null && co2Val >= 800;
  const alertTask = visibleTasks.find(t => t.urgency >= 4);

  // build summary prose from live state (fallback strings if nothing known)
  const summaryProse = useMemo(() => {
    const parts: ReactNode[] = [];
    parts.push(
      <span key="p">
        主室には現在 <span className="wall-num">{presVal}</span>&thinsp;名が滞在しています。
      </span>
    );
    if (co2Flagged) {
      parts.push(
        <span key="c">
          {' '}気温と湿度は安定していますが、CO₂ は徐々に上がっており{' '}
          <span className="wall-em">換気をおすすめします</span>。
        </span>
      );
    } else {
      parts.push(
        <span key="c">
          {' '}気温・湿度・CO₂ ともに安定しています。
        </span>
      );
    }
    if (alertTask) {
      parts.push(
        <span key="a">
          {' '}西側の cam.main_b では <span className="wall-em">姿勢の崩れ</span>を観測しました。
        </span>
      );
    }
    return parts;
  }, [presVal, co2Flagged, alertTask]);

  // group + cap tasks for the manifest
  const tasksTop = visibleTasks.slice(0, 6);
  const nonRoutine = tasksTop.filter(t => t.urgency >= 2);
  const routine    = tasksTop.filter(t => t.urgency < 2);

  // ----------------------------------------------------------------
  // clock & date strings
  // ----------------------------------------------------------------
  const clockTime = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const clockDate = (() => {
    const y = now.getFullYear();
    const m = pad(now.getMonth() + 1);
    const d = pad(now.getDate());
    const wk = ['sun','mon','tue','wed','thu','fri','sat'][now.getDay()];
    return `${y} . ${m} . ${d} — ${wk}`;
  })();

  // ----------------------------------------------------------------
  // render
  // ----------------------------------------------------------------
  return (
    <main className="wall-frame">
      {/* TOP ------------------------------------------------------ */}
      <header className="wall-top">
        <div className="wall-brand">
          soms <span className="wall-brand-dot">·</span> main hub
          <span className="wall-brand-sub">共生観察 / symbiotic observation</span>
        </div>
        <div className="wall-clock">
          <div className="wall-clock-time">{clockTime}</div>
          <div className="wall-clock-date">{clockDate}</div>
        </div>
      </header>

      {/* BODY ----------------------------------------------------- */}
      <section className="wall-body">

        {/* LEFT ---------------------------------------------------- */}
        <div className="wall-col-left">

          {/* §1 今日の様子 ---------------------------------------- */}
          <div className="wall-section-summary">
            <header className="wall-sec-head">
              <span className="wall-sec-num">01</span>
              <h2 className="wall-sec-jp">今日の様子</h2>
              <span className="wall-sec-en">notes from the room</span>
            </header>

            <div className="wall-summary">
              <p className="wall-summary-prose">{summaryProse}</p>

              <dl className="wall-summary-meta">
                <div>
                  <div className="wall-meta-l">cycles · 24h</div>
                  <div className="wall-meta-v">— 回</div>
                </div>
                <div>
                  <div className="wall-meta-l">cameras</div>
                  <div className="wall-meta-v">3 台<span className="wall-accent"> ◯</span></div>
                </div>
                <div>
                  <div className="wall-meta-l">sensors</div>
                  <div className="wall-meta-v">
                    {sensors.length} 台<span className="wall-accent"> ◯</span>
                  </div>
                </div>
                <div>
                  <div className="wall-meta-l">zone</div>
                  <div className="wall-meta-v">主室 / main</div>
                </div>
              </dl>
            </div>
          </div>

          <div className="wall-col-divider" />

          {/* §2 気配 -------------------------------------------- */}
          <div className="wall-section-readings">
            <header className="wall-sec-head">
              <span className="wall-sec-num">02</span>
              <h2 className="wall-sec-jp">気配</h2>
              <span className="wall-sec-en">ambient figures</span>
            </header>

            <div className="wall-readings">
              <ReadingCell
                value={co2Val ?? '—'}
                unit="ppm"
                jp="二酸化炭素"
                en="co₂"
                trend={co2Flagged ? <><span className="wall-warn">▲</span> 高め</> : '— 安定'}
                flagged={co2Flagged}
              />
              <ReadingCell
                value={tempVal ?? '—'}
                unit="℃"
                jp="気温"
                en="temperature"
                trend="— 安定"
              />
              <ReadingCell
                value={humidVal ?? '—'}
                unit="%"
                jp="湿度"
                en="humidity"
                trend="— 安定"
              />
              <ReadingCell
                value={presVal}
                unit="名"
                jp="在室"
                en="presence"
                trend={pres ? 'cam.main_a / b / entry' : '—'}
              />
            </div>
          </div>
        </div>

        {/* RIGHT — §3 お願い -------------------------------------- */}
        <div className="wall-col-right">
          <header className="wall-sec-head">
            <span className="wall-sec-num">03</span>
            <h2 className="wall-sec-jp">お願い</h2>
            <span className="wall-sec-en">tasks for today</span>
          </header>

          <div className="wall-manifest">
            {nonRoutine.length === 0 && routine.length === 0 && (
              <div className="wall-manifest-divider">— 現在、未処理の依頼はありません</div>
            )}

            {nonRoutine.map(t => <NoticeRow key={t.id} task={t} />)}

            {routine.length > 0 && nonRoutine.length > 0 && (
              <div className="wall-manifest-divider">日 常 — routine</div>
            )}

            {routine.map(t => <NoticeRow key={t.id} task={t} />)}
          </div>
        </div>

      </section>

      {/* FOOT ----------------------------------------------------- */}
      <footer className="wall-foot">
        <div className="wall-foot-l">
          <span className="wall-pulse" />observing — 観察中
        </div>
        <div className="wall-foot-c">soms · symbiotic observation &amp; management</div>
        <div className="wall-foot-r">
          {sensorsQuery.isError ? 'sensors offline' : `${sensors.length} sensors / ${visibleTasks.length} active`}
        </div>
      </footer>
    </main>
  );
}

// ==================================================================
// helper sub-components
// ==================================================================

interface ReadingCellProps {
  value: string | number;
  unit: string;
  jp: string;
  en: string;
  trend: ReactNode;
  flagged?: boolean;
}

function ReadingCell({ value, unit, jp, en, trend, flagged }: ReadingCellProps) {
  return (
    <div className={`wall-reading${flagged ? ' wall-reading--flagged' : ''}`}>
      <div className="wall-reading-num">
        {value}<span className="wall-reading-unit">{unit}</span>
      </div>
      <div className="wall-reading-jp">{jp}</div>
      <div className="wall-reading-en">{en}</div>
      <div className="wall-reading-rule" />
      <div className="wall-reading-trend">{trend}</div>
    </div>
  );
}

function NoticeRow({ task }: { task: Task }) {
  const tag = tagFor(task.urgency);
  const zone = zoneLabel(task.zone);
  return (
    <button className={`wall-row${tag.alert ? ' wall-row--alert' : ''}`} type="button">
      <span className={`wall-tag${tag.alert ? ' wall-tag--alert' : ''}`}>{tag.label}</span>
      <span className="wall-num-col">{formatId(task.id)}</span>
      <span className="wall-time-col">{formatHHMM(task.created_at)}</span>
      <span className="wall-title-col">
        {task.title}
        {task.description && (
          <span className="wall-note">{truncate(task.description, 28)}</span>
        )}
      </span>
      <span className="wall-zone-col">
        {zone.en}
        {zone.jp && <span className="wall-zone-jp">{zone.jp}</span>}
      </span>
      <span className="wall-arrow">→</span>
    </button>
  );
}
