export function SkeletonBox({ className = "" }: { className?: string }) {
  return <div className={`skeleton rounded ${className}`} />;
}

export function SkeletonStatCards({ count = 4 }: { count?: number }) {
  return (
    <div className={`grid grid-cols-2 sm:grid-cols-${count} gap-3 mb-6`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-xl border border-gray-100 px-4 py-3">
          <SkeletonBox className="h-3 w-12 mb-2" />
          <SkeletonBox className="h-7 w-16" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTableRows({ cols = 7, rows = 5 }: { cols?: number; rows?: number }) {
  return (
    <tbody className="divide-y divide-gray-50">
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-5 py-3.5">
              <SkeletonBox className={`h-4 ${c === 0 ? "w-20" : c === 1 ? "w-28" : "w-16"}`} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

