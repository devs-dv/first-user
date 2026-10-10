import { RunForm } from "./run-form";

export default function Home() {
  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          Paste your app&apos;s link. A first-time user tries it and tells you where they got stuck.
        </h1>
        <p className="text-lg text-muted">
          You get a step-by-step report with screenshots, the moments they were confused, and whether they reached
          the goal.
        </p>
      </section>

      <RunForm />

      <section className="space-y-2 rounded-xl border border-line bg-surface p-5 text-sm text-muted">
        <h2 className="font-medium text-foreground">What happens when you submit</h2>
        <p>
          We open your site in a real browser and click around like a visitor would. We may create a test account to
          get further. We never enter payment details: if the next step needs a card, the visit stops there.
        </p>
        <p>A run takes a few minutes. You can leave the page and come back to the report link.</p>
      </section>
    </div>
  );
}
