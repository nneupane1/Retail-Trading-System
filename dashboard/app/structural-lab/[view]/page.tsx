import { notFound } from "next/navigation";
import { StructuralLabShell } from "@/components/structural-lab-shell";

const VALID_VIEWS = new Set([
  "overview",
  "market-replay",
  "structure-map",
  "profit-vault",
  "trade-review",
  "settings",
]);

export default async function StructuralLabViewPage({
  params,
}: {
  params: Promise<{ view: string }>;
}) {
  const { view } = await params;
  if (!VALID_VIEWS.has(view)) {
    notFound();
  }
  return <StructuralLabShell view={view as "overview" | "market-replay" | "structure-map" | "profit-vault" | "trade-review" | "settings"} />;
}
