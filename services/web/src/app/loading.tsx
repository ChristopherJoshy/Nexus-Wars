import { Skeleton } from "@/components/ui/skeleton";

export default function GlobalPageLoading() {
  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 space-y-6 font-mono animate-in fade-in-50 duration-200">
      {/* Top Header Skeleton Bar */}
      <div className="flex items-center justify-between p-4 rounded-lg bg-card border border-border">
        <div className="space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-72" />
        </div>
        <Skeleton className="h-8 w-28 rounded-md" />
      </div>

      {/* Grid Content Skeletons */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="md:col-span-2 space-y-4">
          <div className="p-5 rounded-lg bg-card border border-border space-y-4">
            <div className="flex justify-between items-center pb-3 border-b border-border">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 w-20" />
            </div>
            <div className="space-y-3">
              <Skeleton className="h-10 w-full rounded" />
              <Skeleton className="h-10 w-full rounded" />
              <Skeleton className="h-10 w-full rounded" />
              <Skeleton className="h-10 w-full rounded" />
              <Skeleton className="h-10 w-full rounded" />
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="p-5 rounded-lg bg-card border border-border space-y-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-20 w-full rounded-md" />
            <Skeleton className="h-8 w-full rounded-md" />
          </div>
        </div>
      </div>
    </div>
  );
}
