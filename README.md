<div align="center">

<img src="https://firstuser-dv.vercel.app/og.png" alt="First User" width="100%" />

# First User

**Your first user. Before the real ones.**

An AI agent that tries your website like a first-time customer, shows exactly where it gets stuck, gives you a fix prompt, and checks your fix again.

**[Try it live →](https://firstuser-dv.vercel.app)** · **[Demo video](https://x.com/devsdv_/status/2109676330157809764)** · **[Example report](https://firstuser-dv.vercel.app/run/1a8152ed-1689-47fe-bcc7-bbd67938414f)** · **[Build journey](https://firstuser-dv.vercel.app/journey)**

Built solo in three days for **#neatHack** with [neatlogs](https://neatlogs.com), [Entire](https://entire.io) and [cfo.ai](https://cfo.ai).


https://github.com/user-attachments/assets/dac0962b-1bb6-4191-a89d-a7422970dc10


</div>

---

## The problem

Every founder knows this moment.

You spend weeks building something. You ship it. It works for you: you've clicked every button a hundred times. Then real people arrive, and some of them quietly leave.

They don't file bug reports. They don't email you. They get stuck somewhere you never looked, and they're gone.

Testers cost money. Friends are polite. Analytics tell you *that* people dropped off, not *why*.

So I set out to build an AI that uses your website the way a brand-new customer would, and tells you the truth about what happened.

---
<img width="1024" height="1536" alt="Day 1 of #neatHack_ Three Bugs Fixed" src="https://github.com/user-attachments/assets/1852f37f-f03b-450e-a3da-cc5e11b32d8e" />

## Chapter 1: Day one, my agent lied to me

The first version was simple: give it a URL and a goal ("add a plant to the cart and reach checkout"). It opens a real browser, plans, clicks, reads the page and reports back.

It worked. Or so it said.

On Saturday afternoon I was reading the traces in **neatlogs** and saw something uncomfortable. The agent clicked a button and reported **success**. The next time it looked, nothing on the page had changed. It had turned a failed click into a success and moved on. neatlogs flagged it as an incident on its own.

That changed the whole project:

> **The hard part wasn't making an AI click. It was making it honest about what happened.**

---

<img width="1672" height="941" alt="photo_2026-10-12_00-16-21" src="https://github.com/user-attachments/assets/34634815-15a2-41a5-9c42-151706ee3826" />

## Chapter 2: Make it prove everything

From then on, every feature followed one rule: **no claim without evidence.**

| What I built | Why |
|---|---|
| **Recovery ladder** | After every action the agent checks whether the page actually changed. If not, it tries a more physical way of clicking and records what happened. A real trace now reads: `"changed": true, "note": "The first try had no effect; a retry worked."` |
| **Independent verifier** | When the agent says "I reached the goal", a separate check tests the final page against your success condition. No success is self-graded. |
| **Element state, before and after** | A button saying "Added ✓" isn't proof. The cart having the item is. |
| **Blame the right party** | If a site's own scripts fail, the report says so. If *our* browser tool failed, it's listed under "Our agent's own issues", never blamed on your site. |

### Testing the tester

I didn't want to *feel* like it worked, so I built evals: journeys that should succeed on real sites, plus deliberately broken sites where the honest answer is "this doesn't work".

- **7 of 7** achievable journeys verified, **two rounds in a row**
- **0 of 3** broken sites wrongly called a success
- About **1¢ per run**

A small benchmark, early and not a guarantee. One lesson along the way: one round looked wrong because my cloud worker was quietly picking up eval runs too, mixing two versions of the agent into one result. I threw that round out and tagged every run with the worker that ran it. *Measuring an agent means controlling which agent you're measuring.*

---
<img width="2048" height="768" alt="banner" src="https://github.com/user-attachments/assets/4d463dc2-3d6b-4362-9718-6a095d53fc10" />

## Chapter 3: A report a founder can act on

Every report answers three questions:

1. **Will a new user understand it?** A first impression: what it does, who it's for, the main action, what might make someone hesitate.
2. **Can they get value?** A clear verdict: **Got through**, **Stuck**, **Login wall**, **Bot check**, **Unconfirmed** or **Our failure**, with the exact step, a screenshot and the page's own errors.
3. **What should you fix first?** Ranked findings, each labelled by what it rests on: **Observed**, **Verified**, or **Our recommendation**. Each comes with a **structured fix prompt** (problem, expected, evidence, 3–5 acceptance criteria) ready to paste into your coding agent.

---

## Chapter 4: Check again, proving the fix

Finding a bug is half the job. **Check again** re-runs the same journey, **without telling the agent what it found before**, and compares finding by finding:

- **Fixed**: the step was reached and the failure didn't come back
- **Still present**
- **Not reached**: it never got there, so it won't claim anything
- **New**: a problem that wasn't there before

"Not reached" matters. A lazy tool would say "fixed" because it didn't see the error. First User says "I couldn't check that."

### The demo that surprised me

For the demo I built **[Fernleaf](https://fernleaf-demo.vercel.app)**, a fictional plant shop with one planted bug: "Add to cart" shows *Added ✓*, but the cart stays empty and the page throws a `TypeError`.

First User found it: **Stuck**. I fixed it and pressed Check again, expecting a clean pass.

It came back **Stuck again**, this time on checkout. My success condition said "the checkout page shows the plant in the order", and my checkout page had no order summary at all. A bug I hadn't planted and hadn't noticed. It marked the original findings **Fixed**, flagged the new one as **New**, and refused to call it a success.

I added the summary, pressed Check again, and got **Got through, verified by an independent check.**

👉 [See that report](https://firstuser-dv.vercel.app/run/1a8152ed-1689-47fe-bcc7-bbd67938414f)

---

## Chapter 5: Understand before you test

Not every founder knows which journey to test. **Understand mode** reads your site and writes a short, sourced brief: what it claims to do, who it's for, pricing ("not published" if it isn't), each claim marked **Confirmed**, **Inferred** or **Unknown**. Then it suggests the journeys a newcomer would try, each one click from a test.

**Understand → Experience → Improve → Retest.**

---

## How the three tools helped

### 🔍 neatlogs: debugging the agent itself
Every run is traced, with **production, eval and development kept separate** so tests never pollute production. neatlogs raised **five incidents** on my agent:
- **Four were real bugs** I fixed, including the lying click (fixed with trusted physical clicks and the recovery ladder).
- **One was a false alarm**: my own egress security spans had no output. I investigated it and changed them to record their decision (host, port, decision, reason) as guardrail spans.

The tool I used to watch my agent also caught my agent's blind spots. Full notes: **[NEATLOGS_NOTES.md](./NEATLOGS_NOTES.md)**

### 🧭 Entire: the build journey
Every milestone is a checkpoint with the AI coding session behind it, so every feature in the demo traces back to the decision that made it:

| Milestone | Checkpoint |
|---|---|
| Recovery ladder (the fix for the lying click) | [51e480b](https://entire.io/gh/devs-dv/first-user/commit/51e480bc36f25adbd566e63b994c5b952c7b4d27) |
| Independent verifier | [a1188d3](https://entire.io/gh/devs-dv/first-user/commit/a1188d3e37e8150da8d5d37d73bc4b01c6843891) |
| Reload fix: blame the site, not the agent | [527d1d0](https://entire.io/gh/devs-dv/first-user/commit/527d1d03d1329cfc456676bd3c6da1c41d5ec1cc) |
| v6: element state, 7/7 two rounds in a row | [971806a](https://entire.io/gh/devs-dv/first-user/commit/971806a6bebbca69259261dd115bd829edfa0bd4) |
| Report v2: verdicts and structured fix prompts | [8a537bb](https://entire.io/gh/devs-dv/first-user/commit/8a537bbd295c52f9011087100561c8fc07260ace) |
| Check again | [6904a29](https://entire.io/gh/devs-dv/first-user/commit/6904a29c320f147fc6fe5fc4a01619df6a7e0fbb) |
| Understand mode | [cd8eb21](https://entire.io/gh/devs-dv/first-user/commit/cd8eb219e2269084fce3f1f879c27cb13336d5b5) |
| Founder brief and feedback loop | [ebac105](https://entire.io/gh/devs-dv/first-user/commit/ebac10501af538bad4a3f03293ec5d77ae0e7155) |

### 💰 cfo.ai: thinking beyond the code
cfo.ai modelled First User as a business: pricing, cost per run (about 1¢), margins and break-even. Its most useful insight: **one-off website tests don't create recurring revenue.** That's a big reason **Check again** exists. It turns a one-time audit into something founders come back to after every fix.
Plan: **[cfo.ai/s/AOaTCh1FguibmvmV](https://cfo.ai/s/AOaTCh1FguibmvmV)**

---

## Safety: it browses the open web, so it has rules

- Never automates Google or GitHub login; never enters payment details
- Stops at bot checks instead of trying to get past them
- **Hidden text on a page can't steer it** (prompt-injection defence)
- Every outbound connection is checked and recorded
- Test logins are never shown to the model and are deleted after the run

---

## What broke along the way

Three days, solo, plenty broke. A few honest ones:
- A **stale tab** after a deploy hung on "Starting…" → it now notices and reloads itself once.
- A **saved form draft overwrote** the journey picked from a brief → fixed, with a test.
- **Test traces flooded production logs** → tests never export to the live project.
- Some steps showed **no screenshot** → every look step now links one.

All found the same way: by looking at what actually happened, not what I assumed.

---

## Under the hood

```
web/        Next.js app on Vercel: forms, live run page, reports, briefs
worker/     Python agent in Docker on AWS EC2: Stagehand + Chrome, neatlogs tracing
supabase/   Postgres queue, storage, row-level security
evals/      Benchmark cases and runners
demo-shop/  Fernleaf, the fictional shop from the demo
evidence/   Screenshots and notes from the build
```

Model: `claude-haiku-5-5`. Deployment notes: [DEPLOY.md](./DEPLOY.md).

---

## What's next

- Testing with real founders' products (with permission)
- Quieter browsers: turning off Chrome's background network traffic
- A bigger, harder benchmark

---

<div align="center">

**I didn't just build an AI that tests websites. I built one that has to prove what happened.**

**[Try First User →](https://firstuser-dv.vercel.app)**

Built solo by **Divyanshu Verma (DV)**, [@devsdv_](https://x.com/devsdv_) · Team **devs-dv** · #neatHack 2026

</div>

https://github.com/user-attachments/assets/9d59ec75-4637-41b1-8145-53249616ae92

