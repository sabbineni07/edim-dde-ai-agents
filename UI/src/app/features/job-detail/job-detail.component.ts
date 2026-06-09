import { Component, OnInit, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  GenerateRecommendationRequest,
  GenerateRecommendationResponse,
  JobMetricsResponse,
  JobRunSummary,
  RecommendationHistoryEntry,
  WorkspaceAgent,
} from '../../services/api.service';
import {
  daysBetween,
  last30DaysDateStrings,
  sampleDataDateStrings,
} from '../../core/date-range.util';
import { parseApiError } from '../../core/api-error.util';
import { AuthService } from '../../core/services/auth.service';
import { UiHints } from '../../services/api.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './job-detail.component.html',
  styleUrls: ['./job-detail.component.css'],
})
export class JobDetailComponent implements OnInit {
  workspaceId = input.required<string>();
  jobId = input.required<string>();

  metricsData: JobMetricsResponse | null = null;
  runs: JobRunSummary[] = [];
  selectedRunId = '';
  recommendations: RecommendationHistoryEntry[] = [];
  lastResult: GenerateRecommendationResponse | null = null;

  workspaceAgents: WorkspaceAgent[] = [];
  selectedWorkspaceAgentId = '';

  loadingMetrics = true;
  loadingRuns = true;
  loadingRecs = true;
  runningRecommendation = false;
  error = '';
  startDate = '';
  endDate = '';
  includeExplanation = true;

  lifecycleLabels: Record<string, string> = {};
  lifecycleNotes: Record<string, string> = {};
  lifecycleTargetStatus: Record<string, string> = {};
  updatingLifecycle: Record<string, boolean> = {};
  lifecycleFeedback: Record<string, { type: 'success' | 'error'; message: string }> = {};

  uiHints: UiHints | null = null;
  dateRangeWarning = '';

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private auth: AuthService
  ) {}

  /** Signed-in user for lifecycle audit (from login session). */
  get signedInUser(): string {
    const u = this.auth.currentUser;
    return (u?.displayName || u?.username || '').trim();
  }

  ngOnInit(): void {
    this.loadLifecycleMeta();
    this.loadWorkspaceAgents();

    this.api.getUiHints().subscribe({
      next: (hints) => {
        this.uiHints = hints;
        this.syncDatesAndLoad();
      },
    });

    this.route.queryParamMap.subscribe(() => this.syncDatesAndLoad());
  }

  private syncDatesAndLoad(): void {
    const qp = this.route.snapshot.queryParamMap;
    const qs = qp.get('start_date')?.trim();
    const qe = qp.get('end_date')?.trim();

    if (qs && qe) {
      this.startDate = qs;
      this.endDate = qe;
    } else if (this.uiHints) {
      const fallback = this.uiHints.use_local_data
        ? sampleDataDateStrings()
        : last30DaysDateStrings();
      this.startDate = fallback.startDate;
      this.endDate = fallback.endDate;
    } else {
      return;
    }

    this.updateDateRangeWarning();
    this.loadMetrics();
    this.loadRuns();
    this.loadRecommendations();
  }

  updateDateRangeWarning(): void {
    const max = this.uiHints?.guardrail_max_date_range_days ?? 30;
    const span = daysBetween(this.startDate, this.endDate);
    if (span > max) {
      this.dateRangeWarning = `Date range is ${span} days; API allows at most ${max} days per recommendation request.`;
    } else {
      this.dateRangeWarning = '';
    }
  }

  loadLifecycleMeta(): void {
    this.api.getLifecycleMeta().subscribe({
      next: (meta) => {
        this.lifecycleLabels = meta.display_labels || {};
      },
    });
  }

  getLifecycleTarget(requestId: string): string {
    return this.lifecycleTargetStatus[requestId] || '';
  }

  setLifecycleTarget(requestId: string, value: string): void {
    this.lifecycleTargetStatus = { ...this.lifecycleTargetStatus, [requestId]: value };
  }

  setLifecycleNotes(requestId: string, value: string): void {
    this.lifecycleNotes = { ...this.lifecycleNotes, [requestId]: value };
  }

  lifecycleLabel(status: string | undefined): string {
    if (!status) return 'Recommended';
    return this.lifecycleLabels[status] || status;
  }

  apiStatusLabel(rec: RecommendationHistoryEntry): string {
    const s = rec.api_request_status || rec.request_log?.['status'];
    return s ? `API: ${s}` : 'API: –';
  }

  applyLifecycleTransition(rec: RecommendationHistoryEntry): void {
    const target = this.getLifecycleTarget(rec.request_id);
    if (!target) {
      this.lifecycleFeedback[rec.request_id] = {
        type: 'error',
        message: 'Select a status to move to.',
      };
      return;
    }
    const user = this.signedInUser;
    if (!user) {
      this.lifecycleFeedback[rec.request_id] = {
        type: 'error',
        message: 'You must be signed in to update lifecycle status.',
      };
      return;
    }
    this.updatingLifecycle = { ...this.updatingLifecycle, [rec.request_id]: true };
    delete this.lifecycleFeedback[rec.request_id];
    this.api
      .updateRecommendationLifecycle(rec.request_id, {
        status: target,
        changed_by: user,
        notes: this.lifecycleNotes[rec.request_id] || undefined,
      })
      .subscribe({
        next: (res) => {
          const next = { ...this.updatingLifecycle };
          delete next[rec.request_id];
          this.updatingLifecycle = next;
          const targets = { ...this.lifecycleTargetStatus };
          delete targets[rec.request_id];
          this.lifecycleTargetStatus = targets;
          const notes = { ...this.lifecycleNotes };
          delete notes[rec.request_id];
          this.lifecycleNotes = notes;
          const label =
            (res['lifecycle_status_label'] as string) ||
            this.lifecycleLabel(res['lifecycle_status'] as string);
          this.lifecycleFeedback[rec.request_id] = {
            type: 'success',
            message: `Updated to ${label}.`,
          };
          this.loadRecommendations();
        },
        error: (err) => {
          const next = { ...this.updatingLifecycle };
          delete next[rec.request_id];
          this.updatingLifecycle = next;
          const detail = err?.error?.detail;
          const msg =
            typeof detail === 'string'
              ? detail
              : err?.message || 'Failed to update lifecycle status';
          this.lifecycleFeedback[rec.request_id] = { type: 'error', message: msg };
        },
      });
  }

  loadWorkspaceAgents(): void {
    const ws = this.workspaceId();
    this.api.getWorkspaceAgents(ws).subscribe({
      next: (list) => {
        this.workspaceAgents = list;
        if (list.length && !this.selectedWorkspaceAgentId) {
          this.selectedWorkspaceAgentId = list[0].id;
        } else if (
          this.selectedWorkspaceAgentId &&
          !list.some((a) => a.id === this.selectedWorkspaceAgentId)
        ) {
          this.selectedWorkspaceAgentId = list[0]?.id || '';
        }
      },
    });
  }

  /** Agent type for the recommend API — from workspace agent install, or platform default. */
  private resolveAgentId(): string {
    if (this.selectedWorkspaceAgentId) {
      const wa = this.workspaceAgents.find((a) => a.id === this.selectedWorkspaceAgentId);
      if (wa?.agent_id) return wa.agent_id;
    }
    return this.uiHints?.default_agent_id || 'dbx_cluster_tuning_agent';
  }

  loadMetrics(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingMetrics = true;
    this.api.getJobMetrics(ws, j, this.startDate || undefined, this.endDate || undefined).subscribe({
      next: (data) => {
        this.metricsData = data;
        this.loadingMetrics = false;
      },
      error: () => {
        this.loadingMetrics = false;
        this.metricsData = null;
      },
    });
  }

  loadRuns(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingRuns = true;
    this.api.getJobRuns(ws, j, this.startDate || undefined, this.endDate || undefined).subscribe({
      next: (list) => {
        this.runs = list;
        this.loadingRuns = false;
        if (list.length && !this.selectedRunId) {
          this.selectedRunId = list[0].job_run_id;
        } else if (list.length && !list.some((r) => r.job_run_id === this.selectedRunId)) {
          this.selectedRunId = list[0].job_run_id;
        }
      },
      error: () => {
        this.loadingRuns = false;
        this.runs = [];
      },
    });
  }

  loadRecommendations(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingRecs = true;
    this.api.getRecommendations(ws, j, 5).subscribe({
      next: (list) => {
        this.recommendations = list;
        this.loadingRecs = false;
      },
      error: () => {
        this.loadingRecs = false;
        this.recommendations = [];
      },
    });
  }

  selectRun(runId: string): void {
    this.selectedRunId = runId;
  }

  formatCost(summary: Record<string, unknown>): string {
    const usd = summary['total_cost_usd'];
    const tokens = summary['total_tokens'];
    const usdStr = typeof usd === 'number' ? usd.toFixed(4) : '–';
    const tokStr = tokens != null ? String(tokens) : '–';
    return `${usdStr} USD, ${tokStr} tokens`;
  }

  runRecommendation(): void {
    if (!this.selectedRunId) {
      this.error = 'Select a job run first.';
      return;
    }
    const j = this.jobId();
    this.runningRecommendation = true;
    this.error = '';
    this.lastResult = null;
    const body: GenerateRecommendationRequest = {
      agent_id: this.resolveAgentId(),
      job_id: j,
      job_run_id: this.selectedRunId,
      start_date: this.startDate || this.metricsData?.start_date || '',
      end_date: this.endDate || this.metricsData?.end_date || '',
      include_explanation: this.includeExplanation,
    };
    if (this.selectedWorkspaceAgentId) {
      body.workspace_agent_id = this.selectedWorkspaceAgentId;
    }
    this.api.generateRecommendation(body)
      .subscribe({
        next: (res) => {
          this.runningRecommendation = false;
          this.lastResult = res;
          this.loadRecommendations();
        },
        error: (err) => {
          this.runningRecommendation = false;
          this.error = parseApiError(err, 'Recommendation failed');
        },
      });
  }

  historyComparisonCurrent(rec: RecommendationHistoryEntry): Record<string, unknown> | null {
    const block = this.historyComparisonBlock(rec);
    return (block?.['current_configuration'] as Record<string, unknown>) ?? null;
  }

  historyComparisonRecommended(rec: RecommendationHistoryEntry): Record<string, unknown> | null {
    const block = this.historyComparisonBlock(rec);
    return (block?.['recommended_configuration'] as Record<string, unknown>) ?? null;
  }

  private historyComparisonBlock(rec: RecommendationHistoryEntry): Record<string, unknown> | null {
    const comp = rec.comparison;
    if (!comp) return null;
    if (comp['comparison'] && typeof comp['comparison'] === 'object') {
      return comp['comparison'] as Record<string, unknown>;
    }
    if (comp['current_configuration']) return comp;
    return null;
  }

  comparisonCurrent(): Record<string, unknown> | null {
    const comp = this.lastResult?.comparison as Record<string, unknown> | undefined;
    const inner = comp?.['current_configuration'] as Record<string, unknown> | undefined;
    return inner ?? null;
  }

  comparisonRecommended(): Record<string, unknown> | null {
    const comp = this.lastResult?.comparison as Record<string, unknown> | undefined;
    const inner = comp?.['recommended_configuration'] as Record<string, unknown> | undefined;
    return inner ?? null;
  }
}
