// The /journey page's content. Edit freely: the page reads everything from here.
//
// Every number comes from evals/results/*.md or hackathon.md, and the section of hackathon.md it comes from is
// noted next to it. Do not add a number that is not written down in one of those two places.

const REPO = "https://github.com/devs-dv/first-user";
const commit = (sha: string) => `${REPO}/commit/${sha}`;

export type Milestone = {
  version: string;
  title: string;
  broke: string;
  changed: string;
  // A commit on GitHub. Each of these carries an Entire-Checkpoint trailer, so it links the agent session too.
  link: string;
  highlight?: "v6" | "today";
};

export const MILESTONES: Milestone[] = [
  {
    // hackathon.md, 2026-10-10 "Cost controls and reliable clicks"
    version: "Day 1",
    title: "The lying click",
    broke: "The browser tool said 'Add to cart' worked. The cart stayed empty: 0 of 5 attempts got through end to end.",
    changed: "Every action now checks that the page actually changed, and climbs a recovery ladder when it did not: 5 of 5.",
    link: commit("51e480b"),
  },
  {
    // evals/results/v0.md; hackathon.md "Eval harness and v0 baseline"
    version: "v0",
    title: "The first baseline",
    broke: "0 verified goals: nothing checked the agent's own claims. Two runs failed before the first step and two ran out of steps.",
    changed: "Wrote down what \"done\" has to mean, then added an independent check, captured page errors and a mouse-click rung.",
    link: commit("a953b37"),
  },
  {
    // evals/results/v1.md and v2.md; hackathon.md "Verifier with the run's factual record, three verdicts"
    version: "v1–v2",
    title: "The independent verifier",
    broke: "The first verifier saw only the final page, so it rejected goals it could not see being done, and 1 of 3 broken sites was still praised.",
    changed: "The check now reads the run's factual record, never the agent's reasoning, and answers verified, contradicted or unverified.",
    link: commit("a1188d3"),
  },
  {
    // evals/results/v3.md and v4.md; hackathon.md "Security fix: an API key in a trace; verifier calibration; eval v4"
    version: "v3–v4",
    title: "Read-back, and a leaked key",
    broke: "The agent typed a last name into the wrong field and never noticed. Then a neatlogs trace captured an API key.",
    changed: "Typed fields are read back. The key was rotated, and a redaction mask with tests was added before anything else shipped. 0 of 3 broken sites praised.",
    link: commit("7837e62"),
  },
  {
    // evals/results/v5.md; hackathon.md "The two herokuapp eval failures: cause found, v5"
    version: "v5",
    title: "Reload when a site's scripts fail",
    broke: "A test site's own scripts often failed to load, and the visitor carried on with a broken page while the agent took the blame.",
    changed: "The visitor reloads, up to twice, and a page that still cannot load is reported as the site's problem, not ours.",
    link: commit("527d1d0"),
  },
  {
    // evals/results/v6.md and v6b.md; hackathon.md "... v6 / v6b: 7/7 twice"
    version: "v6",
    title: "7 of 7 verified, twice",
    broke: "A button turning green leaves no words to quote, so the check could not confirm it.",
    changed: "Each action records the element's state before and after. 7 of 7 test journeys completed and independently verified, in two consecutive rounds.",
    link: commit("971806a"),
    highlight: "v6",
  },
  {
    // hackathon.md "Report v2", "Understand mode", "Check again", "Founder brief"
    version: "Today",
    title: "Check again, Understand, Founder brief",
    broke: "A report ended the conversation. There was no way to confirm a fix.",
    changed: "Check again compares runs finding by finding. Understand mode suggests journeys. The founder brief reads the public site.",
    link: commit("6904a29"),
    highlight: "today",
  },
];

// The two numbers at the top of the page: evals/results/v0.md (no verifier, so 0 verified) and v6.md / v6b.md.
export const HEADLINE = {
  before: { label: "v0", value: "0", note: "verified goals" },
  after: { label: "v6", value: "7/7", note: "verified, two rounds" },
};

export type Tag = "Found" | "Faced" | "Asked" | "Did";

export type ToolCard = { tag: Tag; title: string; body: string; metric?: string };

export const TOOLS: { tool: string; cards: ToolCard[] }[] = [
  {
    tool: "neatlogs",
    cards: [
      {
        // hackathon.md, 2026-10-10 "Cost controls and reliable clicks" (the before-and-after table)
        tag: "Found",
        title: "The lying click",
        metric: "0/5 → 5/5",
        body: "The trace showed the tool reporting \"clicked Add to cart\" while the cart stayed empty. Fixed with a page-change check and a recovery ladder.",
      },
      {
        // hackathon.md, "Known limitations": about 94% on Haiku 4.5, about 70% now ($0.0033 of $0.0047)
        tag: "Found",
        title: "The hidden bill",
        metric: "94% → 70%",
        body: "Most of a run's cost was the browser library's own lookups: about 94% on Haiku 4.5. Routed through our traced client on Haiku 5.5, about 70%.",
      },
      {
        // evals/results/v0.md and v6.md
        tag: "Did",
        title: "An independent verifier",
        metric: "0 → 7/7",
        body: "Goals verified went from 0 in v0 to 7 of 7 in v6, with 0 of 3 broken sites praised.",
      },
      {
        // hackathon.md, "Security fix: an API key in a trace"
        tag: "Faced",
        title: "A key in a trace, reported",
        body: "A trace recorded an API key passed as a function argument. The key was rotated, traced functions stopped taking secrets, and a redaction mask with tests was added.",
      },
    ],
  },
  {
    tool: "Entire",
    cards: [
      {
        // hackathon.md, "Entire" (checkpoints on every commit)
        tag: "Did",
        title: "Every commit, with its session",
        body: "Every commit carries an Entire checkpoint linking it to the coding-agent session behind it.",
      },
    ],
  },
  {
    tool: "cfo.ai",
    cards: [
      {
        tag: "Did",
        title: "A business plan from the measured cost",
        body: "Pricing, costs and runway were planned from the cost per run measured in the traces.",
      },
    ],
  },
  {
    tool: "Stagehand",
    cards: [
      {
        // hackathon.md, 2026-10-10 "Egress guard in the worker"
        tag: "Found",
        title: "A page could reach the browser's controls",
        body: "The browser was launched in a way that let a visited page connect to its DevTools port. Now only the browser's own extension can, behind a guard with tests.",
      },
    ],
  },
  {
    tool: "Real apps",
    cards: [
      {
        // hackathon.md, "Reports for apps behind a login"
        tag: "Found",
        title: "Most apps hide behind a login",
        body: "That led to the three ways in (a start link, a test login, or letting it sign up) and to a first-impression review that works even when the run stops at a login.",
      },
    ],
  },
];

export const ALSO_BUILT_WITH = ["Claude", "Supabase", "Vercel", "AWS"];

export type Lesson = { title: string; body: string; mistake?: boolean };

export const LESSONS: Lesson[] = [
  {
    title: "A leaked API key",
    body: "An API key was captured in a trace. It was rotated, and a redaction mask with tests was added before anything else shipped.",
    mistake: true,
  },
  { title: "Don't trust the tool's own success message", body: "Check the page, not the return value." },
  { title: "Separate our failures from yours", body: "A report that blames the site for our crash is worse than no report." },
  {
    title: "Most apps hide behind a login",
    body: "That led to the three ways in, and to stating plainly when Google or GitHub sign-in stops a run.",
  },
];

// One run, not a benchmark. The page shows this card only when `result` is filled in, and labels it as a
// single run. Write what the run did in plain words, and link the report.
export const SINGLE_RUNS: { title: string; what: string; result: string; link?: string }[] = [
  {
    title: "Injection test on a demo shop",
    what: "A demo shop page with instructions written into it for the visitor, to see whether it would follow them.",
    result: "", // TODO: what happened in that one run (and set `link` to its report).
  },
];
