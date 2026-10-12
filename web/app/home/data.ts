// The words and the demo data of the home page, from the design (design/code/First User v8.dc.html).
// Numbers here come only from evals/results and hackathon.md.

export const PHASES = ["Understanding the page", "Exploring", "Verifying", "Writing the report"] as const;

// The hero's demo run on a made-up site ("taskpond.app"). It is labelled as a demo on the page.
export type HeroStep = {
  ph: number;
  path: string;
  title: string;
  rows: string[];
  target: string;
  thought: string;
  act: string;
  res: "ok" | "retry" | "done";
};

export const HERO_RUN: HeroStep[] = [
  { ph: 0, path: "/", title: "Plan the week, together.", rows: ["Boards for small teams", "Weekly plan"], target: "Start free", thought: "A project board for small teams. The main thing is creating a project.", act: "Reading the homepage", res: "ok" },
  { ph: 1, path: "/start", title: "Welcome to Taskpond", rows: ["Demo workspace"], target: "Continue", thought: "There is a start link. Using it instead of signing up.", act: "Opening the start link", res: "ok" },
  { ph: 1, path: "/dashboard", title: "Your projects", rows: ["No projects yet"], target: "New project", thought: 'No projects yet. "New project" looks like the way in.', act: "Clicking 'New project'", res: "ok" },
  { ph: 1, path: "/projects/new", title: "New project", rows: ["Launch plan"], target: "Create project", thought: "Named it Launch plan. Creating it.", act: "Clicking 'Create project'", res: "ok" },
  { ph: 1, path: "/projects/new", title: "New project", rows: ["Launch plan"], target: "Create project", thought: "The spinner stopped but the form is still here. Trying again.", act: "Waiting, then clicking again", res: "retry" },
  { ph: 1, path: "/projects/launch-plan", title: "Launch plan", rows: ["To do", "Doing"], target: "Add task", thought: "The project opened. Adding the first task.", act: "Clicking 'Add task'", res: "ok" },
  { ph: 2, path: "/dashboard", title: "Your projects", rows: ["Launch plan · 1 task"], target: "Launch plan", thought: "Checking the dashboard shows the new project.", act: "Checking the dashboard", res: "ok" },
  { ph: 3, path: "/dashboard", title: "Your projects", rows: ["Launch plan · 1 task"], target: "Launch plan", thought: "Done. Writing up what I found.", act: "Writing the report", res: "done" },
];

export const MARQUEE = [
  "Real browser",
  "Independent check",
  "Screenshots on every finding",
  "Captured browser errors",
  "Fix prompts for your coding agent",
  "Check again",
];

export const LOOP = [
  { name: "Understand", body: "Reads your public site and works out what the product does, who it is for and which journeys matter." },
  { name: "Experience", body: "A first-time visitor attempts one goal in a real browser, one action at a time, with a screenshot of every step." },
  { name: "Improve", body: "Each finding comes with evidence and a fix prompt you can paste into your coding agent." },
  { name: "Retest", body: "Check again runs the same goal and tells you what is fixed, still present, new, or not reached." },
];

export const TRUST = [
  "An independent check confirms the result. It never sees the agent's reasoning.",
  "Every finding has a screenshot, a step number and the page it happened on.",
  "Browser errors hidden from the visitor are captured and listed.",
  "Our own failures are kept separate from your site's problems.",
  'When we can\'t confirm something, the report says "couldn\'t confirm" or "not reached".',
];

// evals/results/v6.md and v6b.md: the three broken cases of the eval set.
export const BROKEN_CASES = ["locked_out", "problem_user", "error_user"];

export const WHO = ["Hackathon builders", "Indie founders", "Early-stage SaaS teams", "Developers shipping a first MVP"];

export const FAQ = [
  {
    q: "What if my app needs a login?",
    a: "There are three ways in: a start link (a demo or guest page), a throwaway test login, or letting the visitor sign up by itself. It never signs in with Google or GitHub.",
  },
  { q: "What happens to my test login?", a: "It is never shown to the AI and is deleted after the run." },
  { q: "How long does a run take?", a: "A few minutes. You can watch it live or come back to the report link." },
  {
    q: "What can it not test?",
    a: 'Apps that only allow Google, GitHub or other OAuth sign-in, and sites behind a "verify you are human" check. The report tells you when either stopped the run.',
  },
];

// How the visitor gets in. The values are what POST /api/runs takes.
export type Access = "public" | "link" | "account" | "signup";

export const ACCESS: { id: Access; t: string; d: string }[] = [
  { id: "public", t: "Public pages only", d: "No login. It sees what anyone can see." },
  { id: "link", t: "Start link", d: "A demo or guest page you share." },
  { id: "account", t: "Test login", d: "A throwaway account. Never shown to the AI, deleted after the run." },
  { id: "signup", t: "Let it sign up", d: "It creates its own account, like a new user would." },
];
