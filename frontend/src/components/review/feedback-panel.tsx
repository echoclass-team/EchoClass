"use client";

import type { TeacherFeedback } from "@/types/qa";

const TONE_CONFIG: Record<
  TeacherFeedback["tone"],
  { label: string; color: string }
> = {
  encouraging: { label: "鼓励", color: "text-emerald-600 bg-emerald-50" },
  neutral: { label: "中立", color: "text-slate-600 bg-slate-100" },
  critical: { label: "严格", color: "text-amber-600 bg-amber-50" },
};

function BulletList({
  title,
  items,
  accentColor,
}: {
  title: string;
  items: string[];
  accentColor: string;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-slate-700">{title}</h4>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
            <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${accentColor}`} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FeedbackPanel({ feedback }: { feedback: TeacherFeedback }) {
  const tone = TONE_CONFIG[feedback.tone] ?? TONE_CONFIG.neutral;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
          反馈建议
        </h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tone.color}`}
        >
          {tone.label}
        </span>
      </div>

      <div className="mt-4 space-y-5">
        <BulletList
          title="做得好"
          items={feedback.strengths}
          accentColor="bg-emerald-500"
        />
        <BulletList
          title="可改进"
          items={feedback.improvements}
          accentColor="bg-amber-400"
        />
        <BulletList
          title="下一步建议"
          items={feedback.next_steps}
          accentColor="bg-sky-500"
        />
      </div>
    </div>
  );
}
