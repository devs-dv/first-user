"use client";

import Script from "next/script";
import { useState } from "react";

import { ALSO_BUILT_WITH, TOOLS, type Tag } from "@/content/journey";
import type { PostDay } from "@/content/x-posts";
import { grid } from "@/lib/css";

const TAGS: Record<Tag, { bg: string; dot: string }> = {
  Found: { bg: "var(--green-soft)", dot: "var(--pass)" },
  Faced: { bg: "var(--amber-soft)", dot: "var(--warn)" },
  Asked: { bg: "var(--blue-soft)", dot: "var(--info)" },
  Did: { bg: "var(--s1)", dot: "var(--acc)" },
};
const FILTERS: ("All" | Tag)[] = ["All", "Found", "Faced", "Asked", "Did"];

// "Found. Faced. Asked. Did.": what each tool helped with, filterable by tag.
export function ByTool() {
  const [filter, setFilter] = useState<"All" | Tag>("All");
  const used = new Set(TOOLS.flatMap((group) => group.cards.map((card) => card.tag)));
  const groups = TOOLS.map((group) => ({ ...group, cards: group.cards.filter((card) => filter === "All" || card.tag === filter) })).filter(
    (group) => group.cards.length > 0,
  );
  return (
    <section data-reveal="" data-self="0" className="flex flex-col gap-7" style={{ marginTop: "var(--section-y)" }}>
      <div data-stagger="" className="flex flex-wrap items-end justify-between gap-x-8 gap-y-[18px]">
        <div>
          <span className="fu-eyebrow mb-3.5 block">By tool</span>
          <h2 className="fu-display text-section">
            Found. Faced.
            <br />
            <span className="text-ink4">Asked.</span>{" "}
            <span className="fu-mark" style={{ padding: "0 10px", borderRadius: 10 }}>
              Did.
            </span>
          </h2>
        </div>
        <div role="group" aria-label="Filter by tag" className="flex flex-wrap gap-1.5">
          {FILTERS.filter((tag) => tag === "All" || used.has(tag)).map((tag) => {
            const on = filter === tag;
            return (
              <button
                key={tag}
                type="button"
                aria-pressed={on}
                onClick={() => setFilter(tag)}
                className="flex h-9 cursor-pointer items-center gap-2 whitespace-nowrap rounded-pill border-[1.5px] border-ink px-3.5 font-code text-[12px] font-medium uppercase tracking-[.06em]"
                style={{ background: on ? "var(--ink)" : "var(--s1)", color: on ? "var(--bg)" : "var(--ink)" }}
              >
                <span aria-hidden className="size-[7px] rounded-full border border-ink" style={{ background: tag === "All" ? "var(--ink4)" : TAGS[tag].dot }} />
                {tag}
              </button>
            );
          })}
        </div>
      </div>
      {groups.map((group) => (
        <div key={group.tool} className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-4 border-b-[1.5px] border-ink pb-3.5">
            <h3 className="fu-display text-tool" style={{ lineHeight: 0.9 }}>
              {group.tool}
            </h3>
            <span className="whitespace-nowrap font-code text-[13px] font-medium text-ink3">
              {group.cards.length} {group.cards.length === 1 ? "entry" : "entries"}
            </span>
          </div>
          <ul className="fu-grid-fill m-0 list-none p-0" style={grid("320px")}>
            {group.cards.map((card) => (
              <li
                key={card.title}
                className="fu-lift flex min-h-[220px] flex-col gap-3.5 rounded-card border-[1.5px] border-ink p-[22px]"
                style={{ background: TAGS[card.tag].bg }}
              >
                <span className="flex h-[26px] items-center gap-1.5 self-start whitespace-nowrap rounded-pill bg-ink-fixed px-2.5 font-code text-[11px] font-medium uppercase tracking-[.06em] text-white">
                  <span aria-hidden className="size-1.5 rounded-full" style={{ background: TAGS[card.tag].dot }} />
                  {card.tag}
                </span>
                {card.metric && (
                  <span className="fu-display mt-auto whitespace-nowrap text-metric" style={{ lineHeight: 0.9 }}>
                    {card.metric}
                  </span>
                )}
                <h4 className="m-0 text-[19px] font-semibold leading-[1.3]">{card.title}</h4>
                <p className="m-0 text-[15px] leading-[1.55] text-ink2 fu-pretty">{card.body}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="flex flex-col gap-3.5 pt-2">
        <span className="fu-eyebrow">Also built with</span>
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {ALSO_BUILT_WITH.map((name) => (
            <li key={name} className="flex h-12 items-center whitespace-nowrap rounded-pill border-[1.5px] border-ink bg-s1 px-5 text-[16px] font-semibold transition-transform duration-200 hover:-rotate-3 hover:scale-105 hover:bg-acc-soft">
              {name}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// Only real post addresses on x.com or twitter.com are embedded.
const POST_URL = /^https:\/\/(x|twitter)\.com\/[A-Za-z0-9_]{1,15}\/status\/\d+\/?$/;

// The posts from content/x-posts.ts, embedded with X's own script. Without the script (blocked, offline)
// each post stays a plain link.
export function XPosts({ days }: { days: PostDay[] }) {
  const shown = days.map((day) => ({ ...day, posts: day.posts.filter((url) => POST_URL.test(url)) })).filter((day) => day.posts.length > 0);
  if (shown.length === 0) {
    return (
      <p className="m-0 mt-8 rounded-cardsm border-[1.5px] border-dashed border-ink3 p-6 text-[16px] text-ink2">
        Daily build notes are posted on X with #neatHack.
      </p>
    );
  }
  return (
    <>
      <Script src="https://platform.twitter.com/widgets.js" strategy="lazyOnload" />
      {shown.map((day) => (
        <div key={day.day} data-reveal="" data-self="0" className="mt-10">
          <div data-stagger="" className="flex items-center gap-3 border-b-[1.5px] border-ink pb-3">
            <span className="flex h-[26px] items-center rounded-pill border-[1.5px] border-ink bg-acc px-2.5 font-code text-[12px] font-medium uppercase text-on-acc">
              {day.day}
            </span>
            <span className="text-[20px] font-semibold">{day.date}</span>
          </div>
          <div className="fu-grid-fill mt-4" style={grid("300px", "12px")}>
            {day.posts.map((url) => (
              <div key={url} data-stagger="" className="min-w-0 overflow-hidden">
                <blockquote className="twitter-tweet" data-theme="dark" data-dnt="true">
                  <a href={url} className="fu-link">
                    View the post on X ↗
                  </a>
                </blockquote>
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
