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
import { defaultBrowseDateRange } from '../../core/date-range.util';
import {
  buildDefaultLifecycleNote,
  buildLifecycleNoteContextFromRecommendation,
} from '../../core/lifecycle-notes.util';
import { parseApiError } from '../../core/api-error.util';
import {
  buildHistoryRecommendationExport,
  buildLatestRecommendationExport,
  copyTextToClipboard,
  downloadJsonFile,
  recommendationExportFilename,
  recommendationExportJson,
} from '../../core/recommendation-export.util';
import { AuthService } from '../../core/services/auth.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { BrowseDataCacheService } from '../../core/services/browse-data-cache.service';
import { ToastService } from '../../core/services/toast.service';
import { MarkdownContentComponent } from '../../shared/markdown-content/markdown-content.component';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { ErrorAlertComponent } from '../../shared/error-alert/error-alert.component';
import { BreadcrumbItem } from '../../shared/breadcrumb/breadcrumb.component';
import { UiHints } from '../../services/api.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule, MarkdownContentComponent, PageHeaderComponent, LoadingCardComponent, EmptyStateComponent, ErrorAlertComponent],
  templateUrl: './job-detail.component.html',
  styleUrls: ['./job-detail.component.css'],
})
export class JobDetailComponent implements OnInit {
  workspaceId = input.required<string>();
  jobId = input.required<string>();

  metricsData: JobMetricsResponse | null = null;
  runs: JobRunSummary[] = [];
  selectedClusterId = '';
  readonly runsPageSizeOptions = [10, 25, 50, 100];
  runsPageSize = 10;
  runsCurrentPage = 1;
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
  activeTab: 'runs' | 'metrics' | 'recommendations' | 'history' = 'runs';
  showAdvancedMetrics = false;

  private readonly destroyRef = inject(DestroyRef);
  private lastLoadKey = '';

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private browseCache: BrowseDataCacheService,
    private toast: ToastService
  ) {}

  /** Signed-in user for lifecycle audit (from login session). */
  get signedInUser(): string {
    const u = this.auth.currentUser;
    return (u?.displayName || u?.username || '').trim();
  }

  get breadcrumbs(): BreadcrumbItem[] {
    const jobsLink = {
      workspaceId: this.workspaceId(),
      start_date: this.startDate,
      end_date: this.endDate,
    };
    return [
      { label: 'Workspaces', link: '/app/workspaces' },
      {
        label: 'Jobs',
        link: ['/app/jobs'],
        queryParams: jobsLink,
      },
      { label: this.jobDisplayName },
    ];
  }

  get workspaceDisplayName(): string {
    const fromAgent = this.workspaceAgents.find((wa) => wa.workspace_name)?.workspace_name;
    return fromAgent?.trim() || this.workspaceId();
  }

  get jobDisplayName(): string {
    const name = this.jobAggregateMetrics?.['job_name'];
    if (typeof name === 'string' && name.trim()) return name.trim();
    return this.jobId();
  }

  get jobDetailSubtitle(): string {
    const parts = [`Workspace ${this.workspaceDisplayName}`];
    if (this.startDate && this.endDate) {
      parts.push(`${this.startDate} – ${this.endDate}`);
    }
    return parts.join(' · ');
  }

  get historyCount(): number {
    return this.recommendations.length;
  }

  selectTab(tab: 'runs' | 'metrics' | 'recommendations' | 'history'): void {
    this.activeTab = tab;
  }

  metricGaugeWidth(pct: number | null): number {
    if (pct == null || Number.isNaN(pct)) return 0;
    return Math.min(100, Math.max(0, pct));
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
      const fallback = defaultBrowseDateRange(this.uiHints);
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
    this.runsCurrentPage = 1;

    this.loadMetrics();
    this.loadRuns();
    this.loadRecommendations();
  }

  refreshJobData(): void {
    this.loadError = '';
    this.loadMetrics(true);
    this.loadRuns(true);
    this.loadRecommendations(true);
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

  onLifecycleTargetChange(rec: RecommendationHistoryEntry, value: string): void {
    this.setLifecycleTarget(rec.request_id, value);
    if (!value) {
      this.setLifecycleNotes(rec.request_id, '');
      return;
    }
    this.setLifecycleNotes(
      rec.request_id,
      buildDefaultLifecycleNote(value, this.lifecycleNoteContext(rec))
    );
  }

  private lifecycleNoteContext(rec: RecommendationHistoryEntry) {
    return buildLifecycleNoteContextFromRecommendation(rec, {
      jobId: this.jobId(),
      workspaceId: this.workspaceId(),
      startDate: this.startDate || undefined,
      endDate: this.endDate || undefined,
    });
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
          this.loadRecommendations(true);
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

  loadMetrics(force = false): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    const envId = this.environmentSelection.getSelectedId();
    const connId = this.environmentSelection.getSelectedConnectionId();
    const datasetId = this.environmentSelection.getSelectedDatasetId();
    const cacheKey = this.browseCache.jobMetricsKey(
      envId,
      connId,
      datasetId,
      ws,
      j,
      this.startDate,
      this.endDate
    );
    const cached = !force && this.browseCache.peek<JobMetricsResponse>(cacheKey);
    this.loadingMetrics = !cached;
    this.browseCache
      .get(
        cacheKey,
        () =>
          this.api.browseJobMetrics(
            ws,
            j,
            this.startDate || undefined,
            this.endDate || undefined,
            envId,
            connId,
            datasetId
          ),
        force
      )
      .subscribe({
        next: (data) => {
          this.metricsData = data;
          this.loadingMetrics = false;
        },
        error: (err) => {
          this.loadingMetrics = false;
          this.metricsData = null;
          const status = (err as { status?: number })?.status;
          if (status === 404) {
            return;
          }
          this.reportLoadError(err, 'Failed to load job metrics');
        },
      });
  }

  loadRuns(force = false): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    const envId = this.environmentSelection.getSelectedId();
    const connId = this.environmentSelection.getSelectedConnectionId();
    const datasetId = this.environmentSelection.getSelectedDatasetId();
    const cacheKey = this.browseCache.jobRunsKey(
      envId,
      connId,
      datasetId,
      ws,
      j,
      this.startDate,
      this.endDate
    );
    const cached = !force && this.browseCache.peek<JobRunSummary[]>(cacheKey);
    this.loadingRuns = !cached;
    this.browseCache
      .get(
        cacheKey,
        () =>
          this.api.browseJobRuns(
            ws,
            j,
            this.startDate || undefined,
            this.endDate || undefined,
            envId,
            connId,
            datasetId
          ),
        force
      )
      .subscribe({
        next: (list) => {
          this.runs = list;
          this.loadingRuns = false;
          if (!force) {
            this.runsCurrentPage = 1;
          }
          this.clampRunsPage();
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

  loadRecommendations(force = false): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    const limit = 5;
    const cacheKey = this.browseCache.recommendationsKey(ws, j, limit);
    const cached = !force && this.browseCache.peek<RecommendationHistoryEntry[]>(cacheKey);
    this.loadingRecs = !cached;
    this.browseCache
      .get(cacheKey, () => this.api.getRecommendations(ws, j, limit), force)
      .subscribe({
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

  get totalRuns(): number {
    return this.runs.length;
  }

  get totalRunsPages(): number {
    if (this.totalRuns === 0) return 1;
    return Math.ceil(this.totalRuns / this.runsPageSize);
  }

  get paginatedRuns(): JobRunSummary[] {
    const start = (this.runsCurrentPage - 1) * this.runsPageSize;
    return this.runs.slice(start, start + this.runsPageSize);
  }

  get runsPageRangeStart(): number {
    if (this.totalRuns === 0) return 0;
    return (this.runsCurrentPage - 1) * this.runsPageSize + 1;
  }

  get runsPageRangeEnd(): number {
    return Math.min(this.runsCurrentPage * this.runsPageSize, this.totalRuns);
  }

  get visibleRunsPageNumbers(): number[] {
    const total = this.totalRunsPages;
    if (total <= 1) {
      return total === 1 ? [1] : [];
    }
    const windowSize = 5;
    let start = Math.max(1, this.runsCurrentPage - Math.floor(windowSize / 2));
    let end = Math.min(total, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }

  onRunsPageSizeChange(): void {
    this.runsCurrentPage = 1;
    this.clampRunsPage();
  }

  goToRunsPage(page: number): void {
    const next = Math.min(Math.max(1, page), this.totalRunsPages);
    if (next !== this.runsCurrentPage) {
      this.runsCurrentPage = next;
    }
  }

  goToRunsFirstPage(): void {
    this.goToRunsPage(1);
  }

  goToRunsLastPage(): void {
    this.goToRunsPage(this.totalRunsPages);
  }

  private clampRunsPage(): void {
    if (this.runsCurrentPage > this.totalRunsPages) {
      this.runsCurrentPage = this.totalRunsPages;
    }
    if (this.runsCurrentPage < 1) {
      this.runsCurrentPage = 1;
    }
  }

  selectRun(clusterId: string): void {
    this.selectedClusterId = clusterId;
  }

  /** Aggregated metrics dict when loaded. */
  get jobAggregateMetrics(): Record<string, unknown> | null {
    return this.metricsData?.metrics ?? null;
  }

  /** One-line context for the metrics card header. */
  get metricsSummaryLine(): string {
    const data = this.metricsData;
    const m = data?.metrics;
    if (!m) return '';
    const parts: string[] = [];
    const name = m['job_name'];
    if (typeof name === 'string' && name.trim()) parts.push(name.trim());
    const runs = m['total_runs'];
    if (typeof runs === 'number') parts.push(`${runs} run${runs === 1 ? '' : 's'}`);
    if (data?.start_date && data?.end_date) {
      parts.push(`${data.start_date} – ${data.end_date}`);
    }
    const dur = m['avg_job_run_duration_seconds'];
    if (typeof dur === 'number') parts.push(`avg run ${this.formatDuration(dur)}`);
    return parts.join(' · ');
  }

  metricNumber(key: string): number | null {
    const v = this.jobAggregateMetrics?.[key];
    return typeof v === 'number' && !Number.isNaN(v) ? v : null;
  }

  metricText(key: string): string | null {
    const v = this.jobAggregateMetrics?.[key];
    if (v == null || v === '') return null;
    return String(v);
  }

  formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return secs ? `${mins}m ${secs}s` : `${mins}m`;
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
      environment_id: this.environmentSelection.getSelectedId() || undefined,
      connection_id: this.environmentSelection.getSelectedConnectionId() || undefined,
      dataset_id: this.environmentSelection.getSelectedDatasetId() || undefined,
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
          this.activeTab = 'recommendations';
          this.loadRecommendations(true);
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

  async copyLatestRecommendation(): Promise<void> {
    if (!this.lastResult) return;
    await this.copyRecommendationPayload(
      buildLatestRecommendationExport(this.lastResult, {
        workspaceId: this.workspaceId(),
        jobId: this.jobId(),
      })
    );
  }

  exportLatestRecommendation(): void {
    if (!this.lastResult) return;
    this.exportRecommendationPayload(
      buildLatestRecommendationExport(this.lastResult, {
        workspaceId: this.workspaceId(),
        jobId: this.jobId(),
      })
    );
  }

  async copyHistoryRecommendation(rec: RecommendationHistoryEntry): Promise<void> {
    await this.copyRecommendationPayload(buildHistoryRecommendationExport(rec));
  }

  exportHistoryRecommendation(rec: RecommendationHistoryEntry): void {
    this.exportRecommendationPayload(buildHistoryRecommendationExport(rec));
  }

  private async copyRecommendationPayload(
    payload: ReturnType<typeof buildLatestRecommendationExport>
  ): Promise<void> {
    try {
      await copyTextToClipboard(recommendationExportJson(payload));
      this.toast.success('Recommendation copied to clipboard');
    } catch {
      this.toast.error('Could not copy to clipboard');
    }
  }

  private exportRecommendationPayload(
    payload: ReturnType<typeof buildLatestRecommendationExport>
  ): void {
    try {
      downloadJsonFile(recommendationExportFilename(payload), payload);
      this.toast.success('Recommendation exported');
    } catch {
      this.toast.error('Could not export recommendation');
    }
  }
}
