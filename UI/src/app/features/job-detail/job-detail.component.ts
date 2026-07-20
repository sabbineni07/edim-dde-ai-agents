import { Component, DestroyRef, OnInit, inject, input } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { combineLatest } from 'rxjs';
import {
  ApiService,
  AnalyzeRcaRequest,
  FailedSparkRunSummary,
  GenerateRecommendationRequest,
  GenerateRecommendationResponse,
  JobMetricsResponse,
  JobRunSummary,
  RcaAnalysisResponse,
  RcaHistoryEntry,
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
import {
  isFailedJobRunStatus,
  jobRunStatusBadgeClass,
  jobRunStatusLabel,
} from '../../core/job-run-status.util';

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
  rcaWorkspaceAgents: WorkspaceAgent[] = [];
  selectedRcaWorkspaceAgentId = '';
  failedRuns: FailedSparkRunSummary[] = [];
  selectedFailedRunKey = '';
  rcaHistory: RcaHistoryEntry[] = [];
  lastRcaResult: RcaAnalysisResponse | null = null;
  loadingFailedRuns = false;
  loadingRcaHistory = false;
  runningRca = false;

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
  activeTab: 'runs' | 'metrics' | 'recommendations' | 'history' | 'rca' = 'runs';
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

  get rcaHistoryCount(): number {
    return this.rcaHistory.length;
  }

  get rcaFailedRunCount(): number {
    return this.failedRuns.length;
  }

  get usesInventoryRunStatus(): boolean {
    return this.runs.some((run) => (run.status || '').trim().length > 0);
  }

  readonly jobRunStatusLabel = jobRunStatusLabel;
  readonly jobRunStatusBadgeClass = jobRunStatusBadgeClass;
  readonly isFailedJobRunStatus = isFailedJobRunStatus;

  get selectedFailedRun(): FailedSparkRunSummary | null {
    return this.failedRuns.find((r) => this.failedRunKey(r) === this.selectedFailedRunKey) || null;
  }

  selectTab(tab: 'runs' | 'metrics' | 'recommendations' | 'history' | 'rca'): void {
    this.activeTab = tab;
    if (tab === 'rca') {
      this.loadFailedRuns();
      this.loadRcaHistory();
    }
  }

  failedRunKey(run: FailedSparkRunSummary): string {
    return `${run.job_run_id}|${run.task_key || ''}`;
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
        this.workspaceAgents = list.filter(
          (a) => !a.agent_id || a.agent_id === 'dbx_cluster_tuning_agent'
        );
        this.rcaWorkspaceAgents = list.filter((a) => a.agent_id === 'spark_job_rca_agent');
        if (this.workspaceAgents.length && !this.selectedWorkspaceAgentId) {
          this.selectedWorkspaceAgentId = this.workspaceAgents[0].id;
        } else if (
          this.selectedWorkspaceAgentId &&
          !this.workspaceAgents.some((a) => a.id === this.selectedWorkspaceAgentId)
        ) {
          this.selectedWorkspaceAgentId = this.workspaceAgents[0]?.id || '';
        }
        if (this.rcaWorkspaceAgents.length && !this.selectedRcaWorkspaceAgentId) {
          this.selectedRcaWorkspaceAgentId = this.rcaWorkspaceAgents[0].id;
        } else if (
          this.selectedRcaWorkspaceAgentId &&
          !this.rcaWorkspaceAgents.some((a) => a.id === this.selectedRcaWorkspaceAgentId)
        ) {
          this.selectedRcaWorkspaceAgentId = this.rcaWorkspaceAgents[0]?.id || '';
        }
      },
    });
  }

  loadFailedRuns(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    if (!this.selectedRcaWorkspaceAgentId) {
      this.failedRuns = [];
      return;
    }
    if (this.usesInventoryRunStatus) {
      this.applyInventoryFailedRuns();
      this.enrichFailedRunsFromSparkTelemetry();
      return;
    }
    this.loadingFailedRuns = true;
    this.api
      .getFailedSparkRuns(
        ws,
        j,
        this.selectedRcaWorkspaceAgentId,
        this.startDate || undefined,
        this.endDate || undefined
      )
      .subscribe({
        next: (rows) => {
          this.failedRuns = rows;
          this.loadingFailedRuns = false;
          this.ensureFailedRunSelection();
        },
        error: () => {
          this.failedRuns = [];
          this.loadingFailedRuns = false;
        },
      });
  }

  private applyInventoryFailedRuns(): void {
    this.loadingFailedRuns = false;
    const jobId = this.jobId();
    const workspaceId = this.workspaceId();
    this.failedRuns = this.runs
      .filter((run) => isFailedJobRunStatus(run.status))
      .map((run) => ({
        job_id: jobId,
        job_run_id: run.job_run_id || run.cluster_id,
        job_run_date: run.job_run_date,
        workspace_id: workspaceId,
      }));
    this.ensureFailedRunSelection();
  }

  private enrichFailedRunsFromSparkTelemetry(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    if (!this.selectedRcaWorkspaceAgentId || !this.failedRuns.length) {
      return;
    }
    this.api
      .getFailedSparkRuns(
        ws,
        j,
        this.selectedRcaWorkspaceAgentId,
        this.startDate || undefined,
        this.endDate || undefined
      )
      .subscribe({
        next: (sparkRows) => {
          const byRunId = new Map(sparkRows.map((row) => [row.job_run_id, row]));
          this.failedRuns = this.failedRuns.map((run) => {
            const spark = byRunId.get(run.job_run_id);
            if (!spark) return run;
            return {
              ...run,
              task_key: spark.task_key,
              failure_reason: spark.failure_reason,
              failure_event_count: spark.failure_event_count,
              last_event_ts: spark.last_event_ts,
            };
          });
        },
      });
  }

  private ensureFailedRunSelection(): void {
    if (this.failedRuns.length && !this.selectedFailedRunKey) {
      this.selectedFailedRunKey = this.failedRunKey(this.failedRuns[0]);
      return;
    }
    if (
      this.selectedFailedRunKey &&
      !this.failedRuns.some((run) => this.failedRunKey(run) === this.selectedFailedRunKey)
    ) {
      this.selectedFailedRunKey = this.failedRuns[0] ? this.failedRunKey(this.failedRuns[0]) : '';
    }
  }

  loadRcaHistory(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingRcaHistory = true;
    this.api.getJobRcaHistory(ws, j).subscribe({
      next: (rows) => {
        this.rcaHistory = rows;
        this.loadingRcaHistory = false;
      },
      error: () => {
        this.rcaHistory = [];
        this.loadingRcaHistory = false;
      },
    });
  }

  onRcaAgentChange(): void {
    this.loadFailedRuns();
  }

  runRca(force = false): void {
    const run = this.selectedFailedRun;
    if (!run || !this.selectedRcaWorkspaceAgentId) {
      this.error = 'Select a failed run and an RCA workspace agent first.';
      return;
    }
    const body: AnalyzeRcaRequest = {
      job_run_id: run.job_run_id,
      workspace_agent_id: this.selectedRcaWorkspaceAgentId,
      agent_id: 'spark_job_rca_agent',
      job_id: run.job_id || this.jobId(),
      job_run_date: run.job_run_date,
      task_key: run.task_key,
      workspace_id: this.workspaceId(),
      trigger_source: 'ui',
      force,
    };
    this.runningRca = true;
    this.error = '';
    this.api.analyzeRca(body).subscribe({
      next: (result) => {
        this.lastRcaResult = result;
        this.runningRca = false;
        this.loadRcaHistory();
        this.toast.success(result.cached ? 'Loaded cached RCA' : 'RCA completed');
      },
      error: (err) => {
        this.runningRca = false;
        this.error = parseApiError(err, 'RCA analysis failed');
      },
    });
  }

  viewRcaHistoryEntry(entry: RcaHistoryEntry): void {
    if (entry.result && entry.result.root_cause) {
      this.lastRcaResult = entry.result as RcaAnalysisResponse;
      return;
    }
    this.api.getRca(entry.request_id).subscribe({
      next: (result) => {
        this.lastRcaResult = result;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load RCA');
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
          if (this.activeTab === 'rca') {
            this.loadFailedRuns();
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
    const run = this.runs.find((r) => r.cluster_id === clusterId);
    if (run && isFailedJobRunStatus(run.status)) {
      this.selectedFailedRunKey = this.failedRunKey({
        job_run_id: run.job_run_id || run.cluster_id,
      });
    }
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
    const dbr = this.displayedDbrVersion;
    if (dbr) parts.push(`DBR ${dbr}`);
    const runs = m['total_runs'];
    if (typeof runs === 'number') parts.push(`${runs} run${runs === 1 ? '' : 's'}`);
    if (data?.start_date && data?.end_date) {
      parts.push(`${data.start_date} – ${data.end_date}`);
    }
    const dur = m['avg_job_run_duration_seconds'];
    if (typeof dur === 'number') parts.push(`avg run ${this.formatDuration(dur)}`);
    return parts.join(' · ');
  }

  get selectedRun(): JobRunSummary | null {
    if (!this.selectedClusterId) return null;
    return this.runs.find((r) => r.cluster_id === this.selectedClusterId) ?? null;
  }

  /** DBR version from the selected run, else aggregate metrics for the date range. */
  get displayedDbrVersion(): string | null {
    const fromRun = this.selectedRun?.dbr_version;
    if (typeof fromRun === 'string' && fromRun.trim()) return fromRun.trim();
    const fromAgg = this.jobAggregateMetrics?.['dbr_version'];
    if (typeof fromAgg === 'string' && fromAgg.trim()) return fromAgg.trim();
    return null;
  }

  private sourceValue(source: JobRunSummary | Record<string, unknown> | null, key: string): unknown {
    if (!source) return null;
    return (source as Record<string, unknown>)[key];
  }

  private sourceText(source: JobRunSummary | Record<string, unknown> | null, key: string): string | null {
    const value = this.sourceValue(source, key);
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }

  private sourceNumber(source: JobRunSummary | Record<string, unknown> | null, key: string): number | null {
    const value = this.sourceValue(source, key);
    return typeof value === 'number' && !Number.isNaN(value) ? value : null;
  }

  hasWorkerMetrics(source: JobRunSummary | Record<string, unknown> | null): boolean {
    return (
      this.sourceText(source, 'azure_worker_vm_size') != null ||
      this.sourceNumber(source, 'avg_worker_cpu_utilization_pct') != null ||
      this.sourceNumber(source, 'avg_worker_memory_utilization_pct') != null ||
      this.sourceNumber(source, 'avg_worker_nodes_consumed') != null ||
      this.sourceNumber(source, 'peak_worker_cpu_utilization_pct') != null ||
      this.sourceNumber(source, 'peak_worker_memory_utilization_pct') != null
    );
  }

  workerVmDisplay(source: JobRunSummary | Record<string, unknown> | null): string {
    const workerVm = this.sourceText(source, 'azure_worker_vm_size');
    if (workerVm) return workerVm;
    const driverVm = this.sourceText(source, 'azure_driver_vm_size');
    return driverVm ? `N/A (driver: ${driverVm})` : 'N/A';
  }

  workerMetricNumber(source: JobRunSummary | Record<string, unknown> | null, key: string): number | null {
    if (!this.hasWorkerMetrics(source)) return null;
    return this.sourceNumber(source, key);
  }

  private workerMetricsNoteForSource(source: JobRunSummary | Record<string, unknown> | null): string | null {
    if (this.hasWorkerMetrics(source)) return null;
    const driverVm = this.sourceText(source, 'azure_driver_vm_size');
    return driverVm
      ? `Single-node or driver-only cluster: worker metrics are unavailable, showing driver details (${driverVm}).`
      : 'Worker metrics are unavailable for this selection.';
  }

  get selectedRunWorkerMetricsNote(): string | null {
    return this.workerMetricsNoteForSource(this.selectedRun);
  }

  get aggregateWorkerMetricsNote(): string | null {
    return this.workerMetricsNoteForSource(this.jobAggregateMetrics);
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
