import { RunLoading } from "./run-loading";

// Shown the moment the visitor is sent here, before the page's own render arrives.
export default function Loading() {
  return <RunLoading />;
}
