/** Rolling window aligned with API default when no dates are passed (last 30 days). */
export function last30DaysDateStrings(): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return {
    startDate: start.toISOString().slice(0, 10),
    endDate: end.toISOString().slice(0, 10),
  };
}

/** Sample CSV date range for local development. */
export function sampleDataDateStrings(): { startDate: string; endDate: string } {
  return { startDate: '2024-01-15', endDate: '2024-01-20' };
}

export function daysBetween(start: string, end: string): number {
  const a = new Date(start);
  const b = new Date(end);
  return Math.ceil(Math.abs(b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24)) + 1;
}
