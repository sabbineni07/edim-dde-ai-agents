import { RecommendationHistoryEntry } from '../services/api.service';

/** Context used to build default adoption lifecycle audit notes (RAG-indexed on approve). */
export interface LifecycleNoteContext {
  jobId: string;
  jobRunId?: string;
  workspaceId?: string;
  startDate?: string;
  endDate?: string;
  workloadType?: string;
  currentNodeType?: string;
  currentMinWorkers?: number;
  currentMaxWorkers?: number;
  recommendedNodeType?: string;
  recommendedMinWorkers?: number;
  recommendedMaxWorkers?: number;
  cpuUtilizationPct?: number;
  memoryUtilizationPct?: number;
  reasonCodes?: string[];
  rationale?: string;
}

function asString(value: unknown): string | undefined {
  if (value == null || value === '') return undefined;
  return String(value);
}

function asNumber(value: unknown): number | undefined {
  if (value == null || value === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function comparisonBlock(rec: RecommendationHistoryEntry): Record<string, unknown> | null {
  const comp = rec.comparison;
  if (!comp) return null;
  if (comp['comparison'] && typeof comp['comparison'] === 'object') {
    return comp['comparison'] as Record<string, unknown>;
  }
  if (comp['current_configuration']) return comp;
  return null;
}

/** Build note context from a history row plus optional UI date range. */
export function buildLifecycleNoteContextFromRecommendation(
  rec: RecommendationHistoryEntry,
  overrides?: Pick<LifecycleNoteContext, 'startDate' | 'endDate' | 'workspaceId' | 'jobId'>
): LifecycleNoteContext {
  const block = comparisonBlock(rec);
  const current = (block?.['current_configuration'] || {}) as Record<string, unknown>;
  const recommended = (block?.['recommended_configuration'] || rec.recommendation || {}) as Record<
    string,
    unknown
  >;
  const currentAutoscale = (current['autoscale'] || {}) as Record<string, unknown>;
  const recommendedAutoscale = (recommended['autoscale'] || {}) as Record<string, unknown>;
  const ingest = (rec.recommendation?.['job_run_ingest'] || {}) as Record<string, unknown>;

  return {
    jobId: overrides?.jobId || rec.job_id,
    jobRunId: rec.job_run_id,
    workspaceId: overrides?.workspaceId || rec.workspace_id,
    startDate: overrides?.startDate,
    endDate: overrides?.endDate,
    workloadType: asString(
      ingest['job_type'] || recommended['workload_type'] || recommended['job_type']
    ),
    currentNodeType: asString(current['azure_node_type'] || current['node_type']),
    currentMinWorkers: asNumber(currentAutoscale['min_workers']),
    currentMaxWorkers: asNumber(currentAutoscale['max_workers']),
    recommendedNodeType: asString(recommended['node_type'] || recommended['azure_node_type']),
    recommendedMinWorkers: asNumber(recommendedAutoscale['min_workers'] ?? recommended['min_workers']),
    recommendedMaxWorkers: asNumber(recommendedAutoscale['max_workers'] ?? recommended['max_workers']),
    cpuUtilizationPct: asNumber(ingest['cluster_avg_cpu_utilization_pct_of_ceiling_capacity']),
    memoryUtilizationPct: asNumber(
      ingest['cluster_avg_memory_utilization_pct_of_ceiling_capacity']
    ),
    reasonCodes: rec.reason_codes?.length ? rec.reason_codes : undefined,
    rationale: asString(rec.recommendation?.['rationale']),
  };
}

function identityPhrase(ctx: LifecycleNoteContext): string {
  const parts = [`job ${ctx.jobId}`];
  if (ctx.jobRunId) parts.push(`run ${ctx.jobRunId}`);
  if (ctx.workspaceId) parts.push(`workspace ${ctx.workspaceId}`);
  if (ctx.startDate && ctx.endDate) parts.push(`metrics ${ctx.startDate} to ${ctx.endDate}`);
  return parts.join(', ');
}

function workloadPhrase(ctx: LifecycleNoteContext): string {
  return ctx.workloadType ? `${ctx.workloadType} workload` : 'Databricks job workload';
}

function autoscaleRange(min?: number, max?: number): string | undefined {
  if (min != null && max != null) return `autoscale min ${min} max ${max} workers`;
  if (max != null) return `autoscale max ${max} workers`;
  if (min != null) return `autoscale min ${min} workers`;
  return undefined;
}

function currentClusterPhrase(ctx: LifecycleNoteContext): string | undefined {
  const parts: string[] = [];
  if (ctx.currentNodeType) parts.push(ctx.currentNodeType);
  const scale = autoscaleRange(ctx.currentMinWorkers, ctx.currentMaxWorkers);
  if (scale) parts.push(scale);
  return parts.length ? `current cluster ${parts.join(', ')}` : undefined;
}

function recommendedClusterPhrase(ctx: LifecycleNoteContext): string | undefined {
  const parts: string[] = [];
  if (ctx.recommendedNodeType) parts.push(ctx.recommendedNodeType);
  const scale = autoscaleRange(ctx.recommendedMinWorkers, ctx.recommendedMaxWorkers);
  if (scale) parts.push(scale);
  return parts.length ? `recommended cluster ${parts.join(', ')}` : undefined;
}

function utilizationPhrase(ctx: LifecycleNoteContext): string | undefined {
  const parts: string[] = [];
  if (ctx.cpuUtilizationPct != null) {
    parts.push(`average CPU utilization ${ctx.cpuUtilizationPct}% of ceiling capacity`);
  }
  if (ctx.memoryUtilizationPct != null) {
    parts.push(`average memory utilization ${ctx.memoryUtilizationPct}% of ceiling capacity`);
  }
  return parts.length ? parts.join('; ') : undefined;
}

function reasonCodesPhrase(ctx: LifecycleNoteContext): string | undefined {
  if (!ctx.reasonCodes?.length) return undefined;
  return `sizing signals: ${ctx.reasonCodes.join(', ')}`;
}

function sizingSummary(ctx: LifecycleNoteContext): string {
  const segments = [
    currentClusterPhrase(ctx),
    recommendedClusterPhrase(ctx),
    utilizationPhrase(ctx),
    reasonCodesPhrase(ctx),
  ].filter(Boolean);
  return segments.join('; ');
}

function rationaleSnippet(ctx: LifecycleNoteContext, maxLen = 160): string | undefined {
  if (!ctx.rationale) return undefined;
  const trimmed = ctx.rationale.trim();
  if (trimmed.length <= maxLen) return trimmed;
  return `${trimmed.slice(0, maxLen).trimEnd()}…`;
}

/** Default audit note when the user selects a lifecycle target (editable before submit). */
export function buildDefaultLifecycleNote(
  targetStatus: string,
  ctx: LifecycleNoteContext
): string {
  const identity = identityPhrase(ctx);
  const workload = workloadPhrase(ctx);
  const sizing = sizingSummary(ctx);
  const rationale = rationaleSnippet(ctx);

  switch (targetStatus.toUpperCase()) {
    case 'ACCEPTED':
      return [
        `Databricks cluster sizing adoption — accepted: ${workload} for ${identity}.`,
        sizing,
        rationale ? `Agent rationale: ${rationale}` : undefined,
        'Team reviewed cluster metrics, autoscale worker limits, and VM sizing; accepted for deployment to right-size provisioning.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'DEPLOYED':
      return [
        `Databricks cluster configuration deployed: applied recommended autoscale and VM sizing for ${workload} (${identity}).`,
        sizing,
        'Change applied to the job cluster; worker node family and max workers updated per approved sizing recommendation.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'MONITORING_AND_VALIDATION':
      return [
        `Post-deployment cluster monitoring: validating ${workload} runs after autoscale/VM change (${identity}).`,
        sizing,
        'Observing CPU and memory utilization, worker node consumption, and run stability before final approval.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'APPROVED':
      return [
        `Approved Databricks cluster tuning pattern for similar workloads: ${workload} (${identity}).`,
        sizing,
        rationale ? `Validated rationale: ${rationale}` : undefined,
        'Post-deployment monitoring confirmed stable utilization; approved as validated cluster sizing knowledge for future autoscale and VM recommendations.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'REJECTED':
      return [
        `Cluster sizing recommendation rejected for ${workload} (${identity}).`,
        sizing,
        rationale ? `Review notes: ${rationale}` : undefined,
        'Not adopted — retain as negative signal for similar CPU/memory utilization and autoscale patterns.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'SUPERSEDED':
      return [
        `Superseded cluster sizing recommendation for ${workload} (${identity}).`,
        sizing,
        'Replaced by a newer recommendation with updated metrics or configuration for this job run.',
      ]
        .filter(Boolean)
        .join(' ');

    case 'CANCELLED':
      return [
        `Adoption cancelled for ${workload} cluster sizing (${identity}).`,
        sizing,
        'Deployment or validation stopped before approval; no approved tuning pattern recorded.',
      ]
        .filter(Boolean)
        .join(' ');

    default:
      return [
        `Lifecycle update to ${targetStatus} for Databricks cluster sizing (${identity}).`,
        sizing,
      ]
        .filter(Boolean)
        .join(' ');
  }
}
