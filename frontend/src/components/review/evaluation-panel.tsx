"use client";

import type { EvaluationReport } from "@/types/qa";

const DIMENSION_LABELS: Record<string, string> = {
  accuracy: "知识准确性",
  scaffolding: "引导支架",
  responsiveness: "回应性",
  language: "语言表达",
  misconception_handling: "迷思处理",
};

function dimensionLabel(key: string) {
  return DIMENSION_LABELS[key] ?? key;
}

function ScoreBar({ score, max = 4 }: { score: number; max?: number }) {
  const pct = Math.round((score / max) * 100);
  const color =
    score >= 3 ? "bg-emerald-500" : score >= 2 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-sm font-semibold text-slate-700">
        {score}
      </span>
    </div>
  );
}

export function EvaluationPanel({
  evaluation,
}: {
  evaluation: EvaluationReport;
}) {
  const overallNum =
    typeof evaluation.overall === "number" ? evaluation.overall : null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
        评估报告
      </h3>

      {/* Overall score */}
      <div className="mt-4 flex items-baseline gap-2">
        <span className="text-4xl font-bold text-slate-950">
          {overallNum !== null ? overallNum.toFixed(1) : "—"}
        </span>
        <span className="text-sm text-slate-400">/ 4.0</span>
      </div>

      {/* Dimension scores */}
      {evaluation.scores.length > 0 && (
        <div className="mt-6 space-y-4">
          {evaluation.scores.map((s) => (
            <div key={s.dimension}>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">
                  {dimensionLabel(s.dimension)}
                </span>
              </div>
              <ScoreBar score={s.score} />
              {s.rationale && (
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  {s.rationale}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {evaluation.scores.length === 0 && (
        <p className="mt-4 text-sm text-slate-400">暂无维度评分数据</p>
      )}
    </div>
  );
}
