# First User: business plan
## cfo.ai
- Plan link: 'https://cfo.ai/s/AOaTCh1FguibmvmV'

Built in cfo.ai on 11 October 2026, during neatHack.

**Where the inputs came from.** The cost per run is measured, not estimated: about $0.006 in model calls per visit, taken from neatlogs traces and the worker's own accounting across more than 60 runs (see `evals/results/` and `hackathon.md`). Server and hosting figures are current list prices. Everything about customers, plan mix, churn and growth is an assumption, and is labelled as one. First User has no paying customers yet.

## Headline

- At $19 and $49 a month, the cost of delivering the product is tiny. Gross margin is above 90% on both paid plans.
- The blended plan breaks even at about **5 paying customers** before founder pay, or **89 customers** with a $2,000 monthly founder draw.
- Cheap delivery does not prove recurring demand. The open question is whether founders keep paying after their first audit. Deploy checks and before-and-after comparisons are what make a subscription worth testing.

- Live plan: https://cfo.ai/s/AOaTCh1FguibmvmV

## 1. Pricing and gross margin

Margins allocate shared infrastructure and free-run costs across 200 paying customers.

| Plan | Monthly price | Included runs | Model cost if fully used | Gross margin at 50% usage | Gross margin at full usage |
|---|---|---|---|---|---|
| Free | $0 | 1, one-off | $0.006 per run | Acquisition expense | Acquisition expense |
| Starter | $19 | 30 | $0.18 | 92.1% | 91.7% |
| Pro | $49 | 150 | $0.90 | 94.4% | 93.5% |

These margins include model calls, assumed payment fees, and allocated server, hosting, database and free-run costs. They exclude founder pay, acquisition spending and unmeasured overhead.

**Product recommendation.** Starter sells the first diagnosis. Pro has to sell continuing value: deploy checks, comparisons, and evidence that fixes worked. Keep the run caps; "every deploy" must not imply unlimited usage.

## 2. Unit economics

Assuming 80% Starter and 20% Pro:

| Measure | Value |
|---|---|
| Average revenue per paying customer | $25 a month |
| Average included allowance | 54 runs a month |
| Runs at 50% usage | 27, costing $0.162 in model calls |
| Illustrative payment processing | $1.025 per customer a month |
| Contribution after model calls and payment fees | $23.81 per customer a month, before shared costs |

At full server use, compute adds about $0.002 per run, making model plus server cost about $0.008 per run before hosting and other overhead. Idle capacity costs more per completed run.

Customer acquisition cost and payback are unknown. A contribution-based lifetime value is roughly $476 at an assumed 5% monthly churn, but that is not evidence of real customer lifetime.

## 3. Monthly costs and revenue at scale

Assumptions: 50% run usage, 1,000 free runs a month, paid hosting and database from launch, and the 80/20 plan mix.

| Monthly figure | 50 paying | 200 paying | 1,000 paying |
|---|---|---|---|
| Revenue | $1,250 | $5,000 | $25,000 |
| Servers | $60 | $60 | $60 |
| Hosting and database | $45 | $45 | $45 |
| Model calls, including free runs | $14.10 | $38.40 | $168 |
| Payment processing | $51.25 | $205 | $1,025 |
| **Total delivery cost** | $170.35 | $348.40 | $1,298 |
| **Gross profit** | $1,079.65 | $4,651.60 | $23,702 |
| **Gross margin** | 86.4% | 93.0% | 94.8% |
| Cash profit after $2,000 founder draw* | −$920.35 | $2,651.60 | $21,702 |

\* Before other overhead, taxes and acquisition spending.

At full allowance usage, 1,000 customers need about two servers, with delivery costs of $1,520 a month and a gross margin of 93.9%. Average capacity is not a guarantee about concurrency.

## 4. Break-even

Baseline spending before any customers is **$111 a month**: server $60, hosting and database $45, and 1,000 free runs $6.

| Operating setup | Paying customers needed |
|---|---|
| No founder pay, expected usage | 5 |
| $2,000 founder draw, expected usage | 89 |
| $2,000 founder draw, full usage | 90 |

This covers the modelled costs, not personal expenses during the unpaid period.

## 5. Runway

**With no sales:**

- **$0 funding:** no funded runway. Pre-sales, deferred invoices or another source must cover the first bills.
- **$10,000:** about 10.4 months, assuming six unpaid months followed by a $2,000 monthly founder draw. Month-end cash turns negative in August 2027.
- If founder pay stays at zero, $10,000 covers about 90 months at the $111 baseline. That is not a realistic all-in guarantee.

**Illustrative growth case.** Starting October 2026 with zero customers, adding 10 paying customers a month and losing 5% of opening customers each month:

- About 92 paying customers by September 2027.
- September revenue: $2,298 a month.
- Closing cash: $2,227 with $0 starting cash, or $12,227 with $10,000.
- Neither cash curve runs out within the 12-month forecast.

The bootstrap result depends on getting paying customers immediately and collecting before bills fall due. It is not proof that launch needs no money.

## Biggest risks

1. **One-off demand.** Customers may cancel after the first useful audit.
2. **Positioning.** Usability testing does not deliver users or validate demand.
3. **Free-run abuse.** No-login access needs enforceable limits and a global budget.
4. **Queues and incomplete costs.** Retries, AWS CPU credits, screenshot storage, bandwidth, monitoring and support could exceed the measured costs.
5. **Trust and safety.** Browser actions and screenshots need isolation, safe-action limits and privacy controls.

## What is already in place against those risks

- Free-run limits: 5 runs per visitor per hour and a queue cap of 20, enforced in the web app.
- A per-run budget guardrail: a run stops at $0.30 or 400,000 tokens.
- A network guard that refuses private and internal addresses, Chrome's sandbox on in the worker image, and secrets redacted from traces.
- Test logins held only for the length of a run and never shown to the model.

## Next move

Get ten paying founders, and measure repeat audits and second-month retention.

---

*cfo.ai checked all 12 months of subscribers, revenue, costs and both cash balances against independent arithmetic. Screenshot: `8-cfo-ai-plan.png`.*
