/** Map API error responses to user-facing messages. */

export function parseApiError(err: unknown, fallback = 'Request failed'): string {
  const e = err as {
    status?: number;
    error?: { detail?: unknown; error_code?: string };
    message?: string;
    name?: string;
  };
  if (e?.name === 'TimeoutError' || e?.message?.includes('Timeout')) {
    return 'Request timed out. The data source may be unreachable — check the Databricks connection.';
  }
  const detail = e?.error?.detail;
  const code = e?.error?.error_code;

  if (code === 'NO_JOB_METRICS') {
    return typeof detail === 'string'
      ? detail
      : 'No metrics found for the selected job run. Check cluster/run selection and metrics connection.';
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
  if (e?.status === 500) {
    return typeof detail === 'string'
      ? detail
      : 'Server error while loading data. Check API logs or try again.';
  }
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join('; ');
  }
  return e?.message || fallback;
}
