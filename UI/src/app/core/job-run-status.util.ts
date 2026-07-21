export type JobRunOutcome = 'passed' | 'failed' | 'canceled' | 'running' | 'unknown';

const FAILED_STATUSES = new Set([
  'failed',
  'failure',
  'error',
  'timedout',
  'timeout',
  'timed_out',
]);

const CANCELED_STATUSES = new Set(['canceled', 'cancelled', 'terminated', 'skipped']);

const PASSED_STATUSES = new Set([
  'succeeded',
  'success',
  'passed',
  'completed',
  'complete',
]);

const RUNNING_STATUSES = new Set(['running', 'pending', 'queued', 'in_progress', 'in progress']);

export function normalizeJobRunStatus(status?: string | null): JobRunOutcome {
  const normalized = (status || '').trim().toLowerCase();
  if (!normalized) return 'unknown';
  if (FAILED_STATUSES.has(normalized)) return 'failed';
  if (CANCELED_STATUSES.has(normalized)) return 'canceled';
  if (PASSED_STATUSES.has(normalized)) return 'passed';
  if (RUNNING_STATUSES.has(normalized)) return 'running';
  return 'unknown';
}

export function isFailedJobRunStatus(status?: string | null): boolean {
  return normalizeJobRunStatus(status) === 'failed';
}

export function jobRunStatusLabel(status?: string | null): string {
  const outcome = normalizeJobRunStatus(status);
  switch (outcome) {
    case 'passed':
      return 'Passed';
    case 'failed':
      return 'Failed';
    case 'canceled':
      return 'Canceled';
    case 'running':
      return 'Running';
    default:
      return status?.trim() || 'Unknown';
  }
}

export function jobRunStatusBadgeClass(status?: string | null): string {
  const outcome = normalizeJobRunStatus(status);
  switch (outcome) {
    case 'passed':
      return 'bg-success';
    case 'failed':
      return 'bg-danger';
    case 'canceled':
      return 'bg-warning text-dark';
    case 'running':
      return 'bg-primary';
    default:
      return 'bg-secondary';
  }
}
