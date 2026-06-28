/** Inclusive rolling window ending on the given date (defaults to today). */
export function last7DaysDateStrings(endDate?: string): { startDate: string; endDate: string } {
  const end = endDate ? parseIsoDate(endDate) : new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  return {
    startDate: formatIsoDate(start),
    endDate: formatIsoDate(end),
  };
}

/** @deprecated Prefer last7DaysDateStrings for browse defaults. */
export function last30DaysDateStrings(): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return {
    startDate: formatIsoDate(start),
    endDate: formatIsoDate(end),
  };
}

/** Sample CSV span when ui-hints are unavailable. */
export function sampleDataDateStrings(): { startDate: string; endDate: string } {
  return { startDate: '2026-06-01', endDate: '2026-06-03' };
}

export interface BrowseDateHints {
  use_local_data?: boolean;
  sample_data_start_date?: string;
  sample_data_end_date?: string;
}

/** Default Jobs / Job detail browse window: last 7 days; local CSV clamped to sample span. */
export function defaultBrowseDateRange(hints: BrowseDateHints | null): {
  startDate: string;
  endDate: string;
} {
  if (hints?.use_local_data) {
    const sampleStart = (hints.sample_data_start_date || '').trim();
    const sampleEnd = (hints.sample_data_end_date || '').trim();
    if (sampleStart && sampleEnd) {
      const range = last7DaysDateStrings(sampleEnd);
      if (range.startDate < sampleStart) {
        range.startDate = sampleStart;
      }
      if (range.endDate > sampleEnd) {
        range.endDate = sampleEnd;
      }
      return range;
    }
    return sampleDataDateStrings();
  }
  return last7DaysDateStrings();
}

export function daysBetween(start: string, end: string): number {
  const a = parseIsoDate(start);
  const b = parseIsoDate(end);
  return Math.ceil(Math.abs(b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24)) + 1;
}

function parseIsoDate(value: string): Date {
  return new Date(`${value.trim()}T12:00:00`);
}

function formatIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}
