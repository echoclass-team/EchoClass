/**
 * 将复盘数据组装为 Markdown 字符串并触发浏览器下载。
 *
 * 结构：教案元信息 → 统计概览 → 每个学生的对话记录 → 评估报告 → 反馈建议
 *
 * refs #133 [M3-B6]
 */

import type {
  DialogStateSummary,
  EvaluationReport,
  QASessionStateData,
  RubricScore,
  TeacherFeedback,
} from "@/types/qa";

const STATUS_LABEL: Record<string, string> = {
  resolved: "已解答",
  abandoned: "已放弃",
  pending: "待处理",
  active: "进行中",
};

const SOURCE_LABEL: Record<string, string> = {
  teacher_marked: "教师标记",
  self_resolve: "学生自悟",
  auto_evaluator: "自动评估",
  abandoned: "放弃",
  turn_limit: "轮次上限",
};

const DIMENSION_LABEL: Record<string, string> = {
  MR: "迷思破除",
  KC: "重点覆盖",
  RR: "解决率",
  TQ: "师范生提问质量",
  SS: "学生满意度",
};

function escapeTableCell(value: string): string {
  return value.replaceAll("|", "\\|").replaceAll("\n", "<br>");
}

// --- builders

function sectionLesson(session: QASessionStateData): string {
  const { lesson } = session;
  const lines: string[] = [
    `# ${lesson.topic} — 答疑复盘`,
    "",
    `| 项目 | 内容 |`,
    `| --- | --- |`,
    `| 学科 | ${escapeTableCell(lesson.subject)} |`,
    `| 年级 | ${escapeTableCell(lesson.grade)} |`,
    `| 课题 | ${escapeTableCell(lesson.topic)} |`,
    `| 对话数 | ${session.dialogs.length} |`,
    `| Session ID | \`${session.session_id}\` |`,
  ];
  if (lesson.objectives.length > 0) {
    lines.push("", "## 教学目标", "");
    lesson.objectives.forEach((o, i) => lines.push(`${i + 1}. ${o}`));
  }
  if (lesson.key_points.length > 0) {
    lines.push("", "## 教学重点", "");
    lesson.key_points.forEach((k) => lines.push(`- ${k}`));
  }
  return lines.join("\n");
}

function sectionStats(session: QASessionStateData): string {
  const total =
    session.resolved + session.abandoned + session.pending + session.active;
  const lines: string[] = [
    "## 统计概览",
    "",
    `| 指标 | 数值 |`,
    `| --- | --- |`,
    `| 总问题数 | ${total} |`,
    `| 已解答 | ${session.resolved} |`,
    `| 已放弃 | ${session.abandoned} |`,
    `| 未完成 | ${session.pending + session.active} |`,
  ];
  return lines.join("\n");
}

function sectionDialogs(dialogs: DialogStateSummary[]): string {
  if (dialogs.length === 0) return "";

  const parts: string[] = ["## 对话记录", ""];

  for (const d of dialogs) {
    const status = STATUS_LABEL[d.status] ?? d.status;
    const source = d.resolution_source
      ? SOURCE_LABEL[d.resolution_source] ?? d.resolution_source
      : "—";
    parts.push(
      `### ${d.student_name}`,
      "",
      `- **状态**：${status}`,
      `- **轮次**：${d.turn_count}`,
      `- **解决方式**：${source}`,
      `- **问题预览**：${d.question_preview}`,
      "",
    );

    if (d.history.length > 0) {
      for (const msg of d.history) {
        const role = msg.role === "teacher" ? "🧑‍🏫 老师" : "🙋 学生";
        const prefix = msg.is_new_question ? "（追问）" : "";
        parts.push(`> **${role}**${prefix}：${msg.content}`);
        if (msg.self_resolved) {
          parts.push("> _学生表示已理解_");
        }
        parts.push("");
      }
    } else {
      parts.push("_暂无对话记录_", "");
    }

    parts.push("---", "");
  }

  return parts.join("\n");
}

function formatScore(s: RubricScore): string {
  const dim = DIMENSION_LABEL[s.dimension] ?? s.dimension;
  const bar = "█".repeat(Math.round(s.score)) + "░".repeat(4 - Math.round(s.score));
  const lines = [`- **${dim}**：${bar} ${s.score}/4`];
  if (s.rationale) {
    lines.push(`  - ${s.rationale}`);
  }
  return lines.join("\n");
}

function sectionEvaluation(evaluation: EvaluationReport | null | undefined): string {
  if (!evaluation) return "";
  const overall =
    typeof evaluation.overall === "number"
      ? evaluation.overall.toFixed(1)
      : "—";

  const lines: string[] = [
    "## 评估报告",
    "",
    `**综合评分**：${overall} / 4.0`,
    "",
  ];

  if (evaluation.scores.length > 0) {
    lines.push("### 各维度评分", "");
    evaluation.scores.forEach((s) => lines.push(formatScore(s)));
    lines.push("");
  }

  return lines.join("\n");
}

function sectionFeedback(feedback: TeacherFeedback | null | undefined): string {
  if (!feedback) return "";

  const lines: string[] = ["## 反馈建议", ""];

  if (feedback.strengths.length > 0) {
    lines.push("### 做得好", "");
    feedback.strengths.forEach((s) => lines.push(`- ${s}`));
    lines.push("");
  }
  if (feedback.improvements.length > 0) {
    lines.push("### 可改进", "");
    feedback.improvements.forEach((s) => lines.push(`- ${s}`));
    lines.push("");
  }
  if (feedback.next_steps.length > 0) {
    lines.push("### 下一步建议", "");
    feedback.next_steps.forEach((s) => lines.push(`- ${s}`));
    lines.push("");
  }

  return lines.join("\n");
}

// --- public API

export function buildReviewMarkdown(
  session: QASessionStateData,
  evaluation?: EvaluationReport | null,
  feedback?: TeacherFeedback | null,
): string {
  return [
    sectionLesson(session),
    "",
    sectionStats(session),
    "",
    sectionDialogs(session.dialogs),
    sectionEvaluation(evaluation),
    sectionFeedback(feedback),
    `---`,
    "",
    `> 由 EchoClass 自动生成 · ${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    "",
  ].join("\n");
}

export function downloadMarkdown(content: string, filename: string): void {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
