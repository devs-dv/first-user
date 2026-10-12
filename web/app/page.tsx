import { Suspense } from "react";

import { parseHomeParams, type HomeParams } from "@/lib/brief-logic";

import { Hero } from "./home/hero";
import { DemoRun, Faq, FinalCta, HowItWorks, Results, Trust, WhoItsFor } from "./home/sections";
import { StartSection } from "./home/start-section";

const EMPTY: HomeParams = { mode: "test", url: "", goal: "", success: "", brief: "" };

export default function Home({ searchParams }: PageProps<"/">) {
  return (
    <main>
      <Hero />
      {/* The form can be filled in from the address (a brief's "Test this journey", "Run it again"). Until
          the address is read, the same form shows empty. */}
      <Suspense fallback={<StartSection initial={EMPTY} />}>
        {searchParams.then((raw) => (
          <StartSection initial={parseHomeParams(raw)} />
        ))}
      </Suspense>
      <DemoRun />
      <HowItWorks />
      <Trust />
      <Results />
      <WhoItsFor />
      <Faq />
      <FinalCta />
    </main>
  );
}
