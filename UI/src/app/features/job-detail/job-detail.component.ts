import { Component, DestroyRef, OnInit, inject, input } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { combineLatest } from 'rxjs';
import {
  ApiService,
  GenerateRecommendationRequest,
  GenerateRecommendationResponse,
  JobMetricsResponse,
  JobRunSummary,
  RecommendationHistoryEntry,
  WorkspaceAgent,
} from '../../services/api.service';
import { last30DaysDateStrings, sampleDataDateStrings } from '../../core/date-range.util';
import { parseApiError } from '../../core/api-error.util';
import { AuthService } from '../../core/services/auth.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
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
  selectedClusterId = '';
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
  loadError = '';

  private readonly destroyRef = inject(DestroyRef);
  private lastLoadKey = '';

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService
  ) {}

  /** Signed-in user for lifecycle audit (from login session). */
  get signedInUser(): string {
    const u = this.auth.currentUser;
    return (u?.displayName || u?.username || '').trim();
  }

  ngOnInit(): void {
    this.loadLifecycleMeta();
    this.loadWorkspaceAgents();

    combineLatest([this.api.getUiHints(), this.route.queryParamMap])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(([hints, qp]) => {
        this.uiHints = hints;
        this.syncDatesAndLoad(qp);
      });
  }

  private syncDatesAndLoad(qp: { get: (name: string) => string | null }): void {
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

    const loadKey = `${this.workspaceId()}|${this.jobId()}|${this.startDate}|${this.endDate}`;
    if (loadKey === this.lastLoadKey) {
      return;
    }
    this.lastLoadKey = loadKey;
    this.loadError = '';

    this.loadMetrics();
    this.loadRuns();
    this.loadRecommendations();
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
    this.api
      .browseJobMetrics(
        ws,
        j,
        this.startDate || undefined,
        this.endDate || undefined,
        this.environmentSelection.getSelectedId(),
        this.environmentSelection.getSelectedConnectionId()
      )
      .subscribe({
        next: (data) => {
          this.metricsData = data;
          this.loadingMetrics = false;
        },
        error: (err) => {
          this.loadingMetrics = false;
          this.metricsData = null;
          this.reportLoadError(err, 'Failed to load job metrics');
        },
      });
  }

  loadRuns(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingRuns = true;
    this.api
      .browseJobRuns(
        ws,
        j,
        this.startDate || undefined,
        this.endDate || undefined,
        this.environmentSelection.getSelectedId(),
        this.environmentSelection.getSelectedConnectionId()
      )
      .subscribe({
        next: (list) => {
          this.runs = list;
          this.loadingRuns = false;
          if (list.length && !this.selectedClusterId) {
            this.selectedClusterId = list[0].cluster_id;
          } else if (list.length && !list.some((r) => r.cluster_id === this.selectedClusterId)) {
            this.selectedClusterId = list[0].cluster_id;
          }
        },
        error: (err) => {
          this.loadingRuns = false;
          this.runs = [];
          this.reportLoadError(err, 'Failed to load job runs');
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

  selectRun(clusterId: string): void {
    this.selectedClusterId = clusterId;
  }

  private reportLoadError(err: unknown, fallback: string): void {
    if (this.loadError) return;
    this.loadError = parseApiError(err, fallback);
  }

  formatCost(summary: Record<string, unknown>): string {
    const usd = summary['total_cost_usd'];
    const tokens = summary['total_tokens'];
    const usdStr = typeof usd === 'number' ? usd.toFixed(4) : '–';
    const tokStr = tokens != null ? String(tokens) : '–';
    return `${usdStr} USD, ${tokStr} tokens`;
  }

  runRecommendation(): void {
    if (!this.selectedClusterId) {
      this.error = 'Select a cluster run first.';
      return;
    }
    const j = this.jobId();
    this.runningRecommendation = true;
    this.error = '';
    this.lastResult = null;
    const selectedRun = this.runs.find((r) => r.cluster_id === this.selectedClusterId);
    const body: GenerateRecommendationRequest = {
      agent_id: this.resolveAgentId(),
      job_id: j,
      cluster_id: this.selectedClusterId,
      include_explanation: this.includeExplanation,
    };
    if (selectedRun?.job_run_id) {
      body.job_run_id = selectedRun.job_run_id;
    }
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
