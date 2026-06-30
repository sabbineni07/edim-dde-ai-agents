import {
  GenerateRecommendationResponse,
  RecommendationHistoryEntry,
} from '../services/api.service';

export interface RecommendationExportPayload {
  exported_at: string;
  workspace_id?: string;
  job_id?: string;
  job_run_id?: string;
  cluster_id?: string;
  request_id?: string;
  timestamp?: string;
  lifecycle_status?: string;
  reason_codes?: string[];
  recommendation?: Record<string, unknown>;
  current_configuration?: Record<string, unknown> | null;
  recommended_configuration?: Record<string, unknown> | null;
  guardrail_recommendation?: Record<string, unknown>;
  guardrail_adjustments?: Array<Record<string, unknown>>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  sizing_hints?: Record<string, unknown>;
  llm_recommendation?: Record<string, unknown>;
  cost_usage_summary?: Record<string, unknown>;
}

function historyComparisonBlock(rec: RecommendationHistoryEntry): Record<string, unknown> | null {
  const comp = rec.comparison;
  if (!comp) return null;
  if (comp['comparison'] && typeof comp['comparison'] === 'object') {
    return comp['comparison'] as Record<string, unknown>;
  }
  if (comp['current_configuration']) return comp;
  return null;
}

export function buildLatestRecommendationExport(
  result: GenerateRecommendationResponse,
  context: { workspaceId: string; jobId: string }
): RecommendationExportPayload {
  const comp = result.comparison as Record<string, unknown> | undefined;
  return {
    exported_at: new Date().toISOString(),
    workspace_id: context.workspaceId,
    job_id: context.jobId,
    job_run_id: result.job_run_id,
    cluster_id: result.cluster_id,
    request_id: result.request_id,
    reason_codes: result.reason_codes,
    recommendation: result.recommendation,
    current_configuration: (comp?.['current_configuration'] as Record<string, unknown>) ?? null,
    recommended_configuration: (comp?.['recommended_configuration'] as Record<string, unknown>) ?? null,
    guardrail_recommendation: result.guardrail_recommendation,
    guardrail_adjustments: result.guardrail_adjustments,
    explanation: result.explanation,
    pattern_analysis: result.pattern_analysis,
    risk_assessment: result.risk_assessment,
    sizing_hints: result.sizing_hints,
    llm_recommendation: result.llm_recommendation,
  };
}

export function buildHistoryRecommendationExport(
  rec: RecommendationHistoryEntry
): RecommendationExportPayload {
  const comp = historyComparisonBlock(rec);
  return {
    exported_at: new Date().toISOString(),
    workspace_id: rec.workspace_id,
    job_id: rec.job_id,
    job_run_id: rec.job_run_id,
    request_id: rec.request_id,
    timestamp: rec.timestamp,
    lifecycle_status: rec.lifecycle_status,
    reason_codes: rec.reason_codes,
    recommendation: rec.recommendation,
    current_configuration: (comp?.['current_configuration'] as Record<string, unknown>) ?? null,
    recommended_configuration: (comp?.['recommended_configuration'] as Record<string, unknown>) ?? null,
    explanation: rec.explanation,
    pattern_analysis: rec.pattern_analysis,
    risk_assessment: rec.risk_assessment,
    cost_usage_summary: rec.cost_usage_summary,
  };
}

export function recommendationExportFilename(payload: RecommendationExportPayload): string {
  const job = sanitizeFilenamePart(payload.job_id || 'job');
  const id = sanitizeFilenamePart(payload.request_id || payload.timestamp || 'recommendation');
  return `recommendation-${job}-${id}.json`;
}

function sanitizeFilenamePart(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'recommendation';
}

export function recommendationExportJson(payload: RecommendationExportPayload): string {
  return JSON.stringify(payload, null, 2);
}

export async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error('Copy failed');
  }
}

export function downloadJsonFile(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
