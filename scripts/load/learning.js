// Load profile for the read-heavy learner path.
//
//   BASE_URL=http://127.0.0.1:8010 k6 run scripts/load/learning.js
//
// Thresholds are part of the contract: a run that misses them fails, so the
// numbers committed to the release notes come from a passing run.
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8010";
const EMAIL = `load-${Date.now()}@example.invalid`;
const PASSWORD = "Load-Test-Password-2026";

export const options = {
  scenarios: {
    learners: {
      executor: "ramping-vus",
      startVUs: 2,
      stages: [
        { duration: "15s", target: 10 },
        { duration: "30s", target: 10 },
        { duration: "10s", target: 0 },
      ],
      gracefulRampDown: "5s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{expected_response:true}": ["p(95)<800", "p(99)<1500"],
  },
};

function cookiesFrom(response) {
  const jar = {};
  for (const [name, value] of Object.entries(response.cookies)) {
    jar[name] = value[0].value;
  }
  return jar;
}

export function setup() {
  const register = http.post(`${BASE}/auth/register`, JSON.stringify({ email: EMAIL, password: PASSWORD }), {
    headers: { "Content-Type": "application/json" },
  });
  if (register.status !== 201) {
    throw new Error(`register failed: ${register.status} ${register.body}`);
  }
  const cookies = cookiesFrom(register);
  const csrf = cookies.mentor_csrf;
  const cookie = `mentor_session=${cookies.mentor_session}; mentor_csrf=${csrf}`;
  const onboard = http.post(`${BASE}/onboarding`, JSON.stringify({
    experience_level: "beginner", target_role: "Python Backend", weekly_minutes: 180,
  }), { headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, Cookie: cookie } });
  if (onboard.status !== 200) {
    throw new Error(`onboarding failed: ${onboard.status} ${onboard.body}`);
  }
  return { cookie, csrf };
}

export default function (data) {
  const headers = { Cookie: data.cookie };
  const paths = [
    `${BASE}/learning/overview`,
    `${BASE}/learning/lessons/variables-v1`,
    `${BASE}/learning/today`,
    `${BASE}/health`,
  ];
  for (const url of paths) {
    const response = http.get(url, { headers, tags: { name: url.replace(BASE, "") } });
    check(response, {
      "status is 200": (r) => r.status === 200,
      "json body": (r) => (r.headers["Content-Type"] || "").includes("application/json"),
    });
  }
  sleep(1);
}
