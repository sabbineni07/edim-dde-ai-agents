import { Component, OnInit, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  AgentProfile,
  ApiService,
  GenerateRecommendationResponse,
  JobMetricsResponse,
  JobRunSummary,
  RecommendationHistoryEntry,
} from '../../services/api.service';
import { last30DaysDateStrings } from '../../core/date-range.util';
import { AuthService } from '../../core/services/auth.service';

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

  agentIds: string[] = ['job_run_cluster_sizing'];
  selectedAgentId = 'job_run_cluster_sizing';
  profiles: AgentProfile[] = [];
  selectedProfileId = '';

  loadingMetrics = true;
  loadingRuns = true;
  loadingRecs = true;
  runningRecommendation = false;
  error = '';
  startDate = '';
  endDate = '';
  includeExplanation = false;

  lifecycleLabels: Record<string, string> = {};
  lifecycleNotes: Record<string, string> = {};
  lifecycleTargetStatus: Record<string, string> = {};
  updatingLifecycle: Record<string, boolean> = {};
  lifecycleFeedback: Record<string, { type: 'success' | 'error'; message: string }> = {};

  readonly sampleDataHint =
    'Sample CSV uses 2024-01-15 through 2024-01-20. Adjust the date range if no runs appear.';

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
    const qp = this.route.snapshot.queryParamMap;
    const qs = qp.get('start_date')?.trim();
    const qe = qp.get('end_date')?.trim();
    if (qs && qe) {
      this.startDate = qs;
      this.endDate = qe;
    } else {
      const r = last30DaysDateStrings();
      this.startDate = r.startDate;
      this.endDate = r.endDate;
    }
    this.loadLifecycleMeta();
    this.loadAgents();
    this.refreshData();
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

  loadAgents(): void {
    this.api.getAgents().subscribe({
      next: (res) => {
        const ids = (res.agent_ids || []).filter(
          (id) => id === 'job_run_cluster_sizing' || id !== 'cluster_config'
        );
        this.agentIds = ids.length ? ids : ['job_run_cluster_sizing'];
        if (!this.agentIds.includes(this.selectedAgentId)) {
          this.selectedAgentId = this.agentIds[0];
        }
        this.loadProfiles();
      },
    });
  }

  onAgentChange(): void {
    this.selectedProfileId = '';
    this.loadProfiles();
  }

  loadProfiles(): void {
    this.api.getAgentProfiles(this.selectedAgentId).subscribe({
      next: (list) => {
        this.profiles = list;
      },
    });
  }

  refreshData(): void {
    this.loadMetrics();
    this.loadRuns();
    this.loadRecommendations();
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
    this.api
      .generateRecommendation({
        agent_id: this.selectedAgentId,
        profile_id: this.selectedProfileId || null,
        job_id: j,
        job_run_id: this.selectedRunId,
        start_date: this.startDate || this.metricsData?.start_date || '',
        end_date: this.endDate || this.metricsData?.end_date || '',
        include_explanation: this.includeExplanation,
      })
      .subscribe({
        next: (res) => {
          this.runningRecommendation = false;
          this.lastResult = res;
          this.loadRecommendations();
        },
        error: (err) => {
          this.runningRecommendation = false;
          const detail = err?.error?.detail;
          if (typeof detail === 'string') {
            this.error = detail;
          } else if (Array.isArray(detail)) {
            this.error = detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join('; ');
          } else {
            this.error = err?.message || 'Recommendation failed';
          }
        },
      });
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
