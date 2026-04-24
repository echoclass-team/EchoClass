export type StageOption = {
  id: string;
  name: string;
  badge: string;
  description: string;
  note: string;
};

export type LessonItem = {
  id: string;
  title: string;
  subject: string;
  focus: string;
  source: string;
};

export type StudentProfile = {
  id: string;
  name: string;
  role: string;
  personality: string;
};

export const stageOptions: StageOption[] = [
  {
    id: "primary",
    name: "小学",
    badge: "基础",
    description: "适合课堂节奏更清晰、互动更外显的演练场景。",
    note: "默认推荐",
  },
  {
    id: "junior",
    name: "初中",
    badge: "进阶",
    description: "适合主题推进、提问追问和板书组织的试讲。",
    note: "可切换",
  },
  {
    id: "senior",
    name: "高中",
    badge: "挑战",
    description: "适合更强的逻辑铺陈、概念辨析和课堂节奏控制。",
    note: "偏深度",
  },
  {
    id: "vocational",
    name: "职校",
    badge: "实训",
    description: "适合任务驱动、项目式组织和实操演示。",
    note: "更贴近任务",
  },
];

export const lessonLibrary: LessonItem[] = [
  {
    id: "lesson-reading",
    title: "语文：秋天的雨",
    subject: "语文",
    focus: "朗读、意象理解、课堂提问",
    source: "教案库 / 演示数据",
  },
  {
    id: "lesson-math",
    title: "数学：分数的加减",
    subject: "数学",
    focus: "例题推导、步骤拆解、板书节奏",
    source: "教案库 / 演示数据",
  },
  {
    id: "lesson-english",
    title: "英语：Travel Plans",
    subject: "英语",
    focus: "情境对话、词汇复现、口语互动",
    source: "教案库 / 演示数据",
  },
];

export const students: StudentProfile[] = [
  {
    id: "student-calm",
    name: "安静型学生",
    role: "总是先观察再发言",
    personality: "需要更明确的鼓励与点名",
  },
  {
    id: "student-curious",
    name: "好奇型学生",
    role: "会追问“为什么”",
    personality: "适合开放提问与二次追问",
  },
  {
    id: "student-fast",
    name: "抢答型学生",
    role: "反应快、表达多",
    personality: "需要节奏控制与补充机会",
  },
];

export function getStageById(stageId?: string) {
  return stageOptions.find((item) => item.id === stageId) ?? stageOptions[0];
}

export function getLessonById(lessonId?: string) {
  return lessonLibrary.find((item) => item.id === lessonId) ?? lessonLibrary[0];
}

export function getStudentById(studentId?: string) {
  return students.find((item) => item.id === studentId) ?? students[0];
}

export function buildSetupHref(params: {
  stageId?: string;
  lessonId?: string;
  studentId?: string;
}) {
  const searchParams = new URLSearchParams();

  if (params.stageId) searchParams.set("stage", params.stageId);
  if (params.lessonId) searchParams.set("lesson", params.lessonId);
  if (params.studentId) searchParams.set("student", params.studentId);

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}
