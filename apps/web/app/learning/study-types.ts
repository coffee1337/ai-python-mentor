export type StudyLessonStatus = "completed" | "available" | "locked";

export type StudyToday = {
  schema_version: 1;
  as_of: string;
  next_lesson: {
    id: string;
    title: string;
    minutes: number;
    is_resume: boolean;
  } | null;
  due_reviews: {
    skill_id: string;
    scheduled_for: string;
    overdue_days: number;
  }[];
  focus: {
    kind: "lesson" | "review";
    lesson_id: string | null;
    skill_id: string;
    title: string;
    estimated_minutes: number;
    reason_codes: string[];
  }[];
  estimated_minutes: number;
  target_minutes: number;
  source: "curriculum" | "starter" | "course";
};

export type StudyProgressDay = {
  date: string;
  activity_count: number;
  lessons_completed: number;
  acquisition_observations: number;
  independent_observations: number;
  assisted_observations: number;
  review_observations: number;
  coding_submissions: number;
};

export type StudyProgressSkill = {
  skill_id: string;
  name: string;
  knowledge_score: number | null;
  practice_score: number | null;
  independent_score: number | null;
  retention_score: number | null;
  acquisition_observations: number;
  review_observations: number;
  last_observed_at: string | null;
  next_review_at: string | null;
  lesson_id: string | null;
  lesson_status: StudyLessonStatus | null;
};

export type StudyActivity = {
  kind: "lesson" | "assessment" | "knowledge_check" | "coding" | "review";
  occurred_at: string;
  skill_id: string | null;
  lesson_id: string | null;
  title: string;
  assisted: boolean | null;
  hint_count: number | null;
  outcome: string;
  evidence_recorded: boolean;
};

export type StudyProgress = {
  schema_version: 1;
  as_of: string;
  window: {
    days: number;
    start_date: string;
    end_date: string;
    utc_offset_minutes: number;
  };
  totals: {
    completed_lessons: number;
    total_lessons: number;
    observed_skills: number;
    due_reviews: number;
  };
  period: {
    active_days: number;
    lessons_completed: number;
    checks_attempted: number;
    checks_passed: number;
    coding_submissions: number;
    acquisition_observations: number;
    independent_observations: number;
    assisted_observations: number;
    review_observations: number;
  };
  days: StudyProgressDay[];
  skills: StudyProgressSkill[];
  recent_activity: StudyActivity[];
};
