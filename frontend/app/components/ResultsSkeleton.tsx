"use client";

/**
 * ResultsSkeleton — shown while the analysis runs (a few seconds: model
 * load + live APIs). Mirrors the results layout with shimmering
 * placeholders so the wait feels intentional, not broken.
 */
export default function ResultsSkeleton() {
  return (
    <div className="mx-auto mt-10 max-w-[1120px]">
      <div className="grid animate-pulse gap-[18px] md:grid-cols-3">
        {/* wide roof card */}
        <div className="col-span-full flex flex-col gap-6 rounded-[20px] border border-sunset-line bg-white p-6 md:flex-row">
          <div className="h-[180px] w-[280px] flex-shrink-0 rounded-[14px] bg-sunset-line" />
          <div className="flex-1 space-y-3">
            <div className="h-3 w-24 rounded bg-sunset-line" />
            <div className="h-8 w-40 rounded bg-sunset-line" />
            <div className="h-3 w-64 rounded bg-sunset-line" />
            <div className="h-2.5 w-full rounded-full bg-sunset-line" />
          </div>
        </div>

        {/* three metric cards */}
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-[20px] border border-sunset-line bg-white p-6 space-y-3">
            <div className="h-3 w-28 rounded bg-sunset-line" />
            <div className="h-9 w-32 rounded bg-sunset-line" />
            <div className="h-3 w-40 rounded bg-sunset-line" />
          </div>
        ))}

        {/* chart */}
        <div className="col-span-full h-[280px] rounded-[20px] border border-sunset-line bg-white p-6">
          <div className="h-3 w-40 rounded bg-sunset-line" />
          <div className="mt-6 flex h-[200px] items-end gap-2">
            {Array.from({ length: 12 }).map((_, i) => (
              <div
                key={i}
                className="flex-1 rounded-t bg-sunset-line"
                style={{ height: `${30 + ((i * 37) % 70)}%` }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
