/** Map API error responses to user-facing messages. */

export function parseApiError(err: unknown, fallback = 'Request failed'): string {
  const e = err as {
    status?: number;
    error?: { detail?: unknown; error_code?: string };
    message?: string;
  };
  const detail = e?.error?.detail;
  const code = e?.error?.error_code;

  if (code === 'NO_JOB_METRICS') {
    return 'No metrics found for this job run in the selected date range. Try sample dates or widen the range.';
  }
  if (code === 'AZURE_OPENAI_NOT_CONFIGURED') {
    return 'Azure OpenAI is not configured. Set AZURE_OPENAI_* in the API environment.';
  }
  if (e?.status === 422) {
    return typeof detail === 'string' ? detail : 'Invalid request (check dates and required fields).';
  }
  if (e?.status === 404) {
    return typeof detail === 'string' ? detail : 'Not found.';
  }
  if (e?.status === 503) {
    return typeof detail === 'string' ? detail : 'Service unavailable.';
  }
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join('; ');
  }
  return e?.message || fallback;
}
