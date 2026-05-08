"use client";

import type { DialogStateSummary } from "@/types/qa";

function roleBadge(role: "teacher" | "student") {
  if (role === "teacher") {
    return (
      <span className="shrink-0 rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
        老师
      </span>
    );
  }
  return (
    <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
      学生
    </span>
  );
}

export function DialogReplay({
  dialogs,
  activeId,
  onSelect,
}: {
  dialogs: DialogStateSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const active = dialogs.find((d) => d.id === activeId);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white">
      {/* Student tab strip */}
      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50 px-3 py-2">
        {dialogs.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => onSelect(d.id)}
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium transition ${
              d.id === activeId
                ? "bg-slate-950 text-white"
                : "bg-white text-slate-600 hover:bg-slate-100"
            }`}
          >
            {d.student_name}
            <span className="ml-1 opacity-60">({d.turn_count}轮)</span>
          </button>
        ))}
      </div>

      {/* Chat messages */}
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {!active && (
          <p className="py-8 text-center text-sm text-slate-400">
            选择一个学生查看对话记录
          </p>
        )}
        {active && active.history.length === 0 && (
          <p className="py-8 text-center text-sm text-slate-400">
            该学生暂无对话记录
          </p>
        )}
        {active?.history.map((msg, idx) => {
          const isTeacher = msg.role === "teacher";
          return (
            <div
              key={idx}
              className={`flex gap-2 ${isTeacher ? "justify-end" : "justify-start"}`}
            >
              {!isTeacher && roleBadge(msg.role)}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  isTeacher
                    ? "bg-sky-600 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                {msg.is_new_question && (
                  <span className="mb-1 block text-xs font-medium opacity-70">
                    [追问]
                  </span>
                )}
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.self_resolved && (
                  <span className="mt-1 block text-xs opacity-70">
                    学生表示已理解
                  </span>
                )}
              </div>
              {isTeacher && roleBadge(msg.role)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
