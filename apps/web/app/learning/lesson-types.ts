export type PathSummary = {
  completed: number;
  total: number;
  next_lesson_id: string | null;
  lessons: {
    id: string;
    title: string;
    minutes: number;
    status: "completed" | "available" | "locked";
  }[];
};

export type Lesson = {
  id: string;
  title: string;
  skill_id: string;
  minutes: number;
  body: string;
  example: string;
  example_output?: string | null;
  question: string;
  choices: string[];
  goal?: string | null;
  theory?: string | null;
  conclusion?: string | null;
  checkpoint?: { prompt: string; choices: string[] } | null;
  misconception?: string | null;
  misconception_check?: { misconception: string; prompt: string } | null;
  practice?: string | null;
  prerequisites?: string[];
  difficulty?: number | null;
  version?: string | null;
};

export type Attempt = {
  id: string;
  status: string;
  result: { message?: string; tests_passed?: number; tests_total?: number };
  created_at: string;
};

export type CheckQuestion = { id: string; prompt: string; choices: string[] };

export type CheckResult = {
  lesson_id: string;
  score: number;
  passed: boolean;
  explanations: {
    question_id: string;
    explanation: string;
    selected_explanation?: string | null;
    correct: string;
  }[];
  recommendation: string;
  recommended_lesson_id: string | null;
};

export type Curriculum = {
  sessions: {
    planned_minutes: number;
    target_minutes: number;
    rationale: string;
    activities: {
      kind?: string;
      lesson_id: string | null;
      skill_id: string;
      estimated_minutes: number;
      reason_codes: string[];
    }[];
  }[];
};

export type AIPlan = {
  status: string;
  model_id?: string;
  steps: {
    position: number;
    skill_id: string;
    kind: string;
    duration_minutes: number;
    title: string;
    explanation: string;
    exercise: {
      prompt: string;
      submission_type: string;
      starter_code?: string;
      constraints: string[];
      runner_status?: string;
    };
  }[];
};

export type MistakeMemory = {
  error_text: string;
  remediation_text: string;
  remediation_exercise_id: string;
  last_seen_at: string;
};
