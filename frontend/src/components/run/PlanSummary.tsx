import { ListChecks, Search } from "lucide-react";
import type { ExecutionPlan } from "../../lib/types";
import { Meta } from "../ui/Panel";
import { EmptyState } from "../ui/States";

const plannerLabel: Record<ExecutionPlan["planner"], string> = {
  llm: "LLM planner",
  heuristic: "Heuristic planner",
  heuristic_fallback: "Heuristic (LLM fallback)",
  deterministic: "Deterministic planner",
};

export function PlanSummary({ plan, active }: { plan: ExecutionPlan | null; active: boolean }) {
  if (!plan) return <EmptyState icon={ListChecks} title={active ? "Planning…" : "No plan recorded"} description={active ? "The plan appears once the agent has interpreted the goal." : undefined} />;
  return (
    <div className="space-y-5 p-4">
      <p className="text-[14px] leading-relaxed text-fg-2">{plan.summary}</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Meta label="Topic">{plan.config.topic}</Meta>
        <Meta label="Audience">{plan.config.audience}</Meta>
        <Meta label="Articles" mono>
          {plan.config.article_count}
        </Meta>
        <Meta label="Lookback" mono>
          {plan.config.lookback_days}d
        </Meta>
      </dl>
      <section>
        <h3 className="eyebrow mb-2">Research queries</h3>
        <ul className="space-y-1.5">
          {plan.research_queries.map((q) => (
            <li key={q} className="flex items-start gap-2 text-[13px] text-fg-2">
              <Search size={13} className="mt-0.5 shrink-0 text-fg-3" aria-hidden />
              <span className="mono text-[12px]">{q}</span>
            </li>
          ))}
        </ul>
      </section>
      {plan.output_requirements.length > 0 && (
        <section>
          <h3 className="eyebrow mb-2">Output requirements</h3>
          <ul className="list-disc space-y-1 pl-4 text-[13px] text-fg-2">
            {plan.output_requirements.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}
      {plan.assumptions.length > 0 && (
        <section>
          <h3 className="eyebrow mb-2">Assumptions</h3>
          <ul className="list-disc space-y-1 pl-4 text-[13px] text-fg-3">
            {plan.assumptions.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="mono text-[11px] text-fg-3">{plannerLabel[plan.planner]}</p>
    </div>
  );
}
