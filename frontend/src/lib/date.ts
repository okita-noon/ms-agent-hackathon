const JST_TIME_ZONE = "Asia/Tokyo";

export function todayJst(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: JST_TIME_ZONE });
}

export function offsetDate(base: string, days: number): string {
  const [year, month, day] = base.split("-").map(Number);
  const dt = new Date(year, month - 1, day + days);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}
