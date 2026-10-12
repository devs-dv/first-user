// Site-wide constants: the navigation, the example report, and the builder's links.

// A real, finished report from the database, shown as "Example report" in the navigation
// (saucedemo.com with its problem_user, see hackathon.md, 2026-10-12).
export const EXAMPLE_REPORT_ID = "91e44505-dade-461a-8882-5a256b73b9ee";
export const EXAMPLE_REPORT_HREF = `/run/${EXAMPLE_REPORT_ID}`;

// The site the hero's "Try" button fills in: the public demo shop the eval set uses.
export const EXAMPLE_SITE = "saucedemo.com";

export const FORM_ANCHOR = "fu-form";

export type NavItem = { label: string; href: string; match: (path: string) => boolean };

export const NAV_ITEMS: NavItem[] = [
  { label: "How it works", href: "/#fu-how", match: () => false },
  { label: "Example report", href: EXAMPLE_REPORT_HREF, match: (path) => path === EXAMPLE_REPORT_HREF },
  { label: "Build Journey", href: "/journey", match: (path) => path === "/journey" },
  { label: "About", href: "/about", match: (path) => path === "/about" },
];

export const SOCIAL = {
  x: { label: "X", handle: "@devsdv_", href: "https://x.com/devsdv_" },
  linkedin: {
    label: "LinkedIn",
    handle: "dev-divyanshuverma",
    href: "https://www.linkedin.com/in/dev-divyanshuverma",
  },
  github: { label: "GitHub", handle: "devs-dv", href: "https://github.com/devs-dv" },
  repo: { label: "Repo", handle: "devs-dv/first-user", href: "https://github.com/devs-dv/first-user" },
} as const;

export const BUILT_WITH = ["neatlogs", "Entire", "cfo.ai", "Stagehand", "Claude", "Supabase", "Vercel", "AWS"];
