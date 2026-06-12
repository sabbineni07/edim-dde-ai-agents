import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, JobSummary, UiHints, Workspace } from '../../services/api.service';
import {
  daysBetween,
  last30DaysDateStrings,
  sampleDataDateStrings,
} from '../../core/date-range.util';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';

@Component({
  selector: 'app-jobs-list',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './jobs-list.component.html',
  styleUrls: ['./jobs-list.component.css'],
})
export class JobsListComponent implements OnInit {
  workspaceId: string | null = null;
  workspaces: Workspace[] = [];
  workspacesLoading = true;
  startDate = '';
  endDate = '';
  jobs: JobSummary[] = [];
  loading = true;
  error = '';
  dateRangeWarning = '';
  filterText = '';
  uiHints: UiHints | null = null;

  constructor(
    private api: ApiService,
    private router: Router,
    private route: ActivatedRoute,
    private workspaceSelection: WorkspaceSelectionService,
    private environmentSelection: EnvironmentSelectionService
  ) {}

  ngOnInit(): void {
    if (!this.environmentSelection.getSelectedId()) {
      void this.router.navigate(['/app/workspaces']);
      return;
    }

    this.api.getUiHints().subscribe({
      next: (hints) => {
        this.uiHints = hints;
        this.syncFromQueryParams(this.route.snapshot.queryParams);
      },
    });

    this.loadWorkspaces();

    this.route.queryParams.subscribe((qp) => this.syncFromQueryParams(qp));
  }

  private loadWorkspaces(): void {
    const envId = this.environmentSelection.getSelectedId();
    this.workspacesLoading = true;
    this.api.getWorkspaces(envId, this.environmentSelection.getSelectedConnectionId()).subscribe({
      next: (list) => {
        this.workspaces = list;
        this.workspacesLoading = false;
        this.syncFromQueryParams(this.route.snapshot.queryParams);
      },
      error: () => {
        this.workspacesLoading = false;
        this.syncFromQueryParams(this.route.snapshot.queryParams);
      },
    });
  }

  private syncFromQueryParams(qp: Record<string, unknown>): void {
    const s = typeof qp['start_date'] === 'string' ? qp['start_date'].trim() : '';
    const e = typeof qp['end_date'] === 'string' ? qp['end_date'].trim() : '';
    let wsId = typeof qp['workspaceId'] === 'string' ? qp['workspaceId'].trim() : '';

    if (!wsId && !this.workspacesLoading && this.workspaces.length > 0) {
      wsId = this.resolveDefaultWorkspaceId();
      const defaults = this.defaultDateRange();
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: {
          workspaceId: wsId,
          start_date: s || defaults.startDate,
          end_date: e || defaults.endDate,
        },
        replaceUrl: true,
      });
      return;
    }

    if (
      wsId &&
      !this.workspacesLoading &&
      this.workspaces.length > 0 &&
      !this.workspaces.some((w) => w.workspace_id === wsId)
    ) {
      wsId = this.resolveDefaultWorkspaceId();
      const defaults = this.defaultDateRange();
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: {
          workspaceId: wsId,
          start_date: s || defaults.startDate,
          end_date: e || defaults.endDate,
        },
        replaceUrl: true,
      });
      return;
    }

    if (!wsId) {
      this.workspaceId = null;
      this.loading = this.workspacesLoading;
      this.jobs = [];
      return;
    }

    this.workspaceSelection.setLastWorkspaceId(wsId);
    this.workspaceId = wsId;

    if (!s || !e) {
      const defaults = this.defaultDateRange();
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: {
          workspaceId: wsId,
          start_date: defaults.startDate,
          end_date: defaults.endDate,
        },
        replaceUrl: true,
      });
      return;
    }

    this.startDate = s;
    this.endDate = e;
    this.updateDateRangeWarning();
    this.load();
  }

  private updateDateRangeWarning(): void {
    const max = this.uiHints?.guardrail_max_date_range_days ?? 30;
    const span = daysBetween(this.startDate, this.endDate);
    if (span > max) {
      this.dateRangeWarning = `Date range is ${span} days; maximum allowed is ${max} days. Narrow the range to load jobs.`;
    } else {
      this.dateRangeWarning = '';
    }
  }

  private resolveDefaultWorkspaceId(): string {
    const last = this.workspaceSelection.getLastWorkspaceId();
    if (last && this.workspaces.some((w) => w.workspace_id === last)) {
      return last;
    }
    return this.workspaces[0].workspace_id;
  }

  private defaultDateRange(): { startDate: string; endDate: string } {
    if (this.uiHints && !this.uiHints.use_local_data) {
      return last30DaysDateStrings();
    }
    return sampleDataDateStrings();
  }

  onWorkspaceChange(workspaceId: string): void {
    if (!workspaceId || workspaceId === this.workspaceId) return;
    this.workspaceSelection.setLastWorkspaceId(workspaceId);
    const defaults = this.defaultDateRange();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        workspaceId,
        start_date: this.startDate || defaults.startDate,
        end_date: this.endDate || defaults.endDate,
      },
      replaceUrl: true,
    });
  }

  applyDateRangeToUrl(): void {
    if (!this.workspaceId) return;
    this.updateDateRangeWarning();
    if (this.dateRangeWarning) return;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        workspaceId: this.workspaceId,
        start_date: this.startDate,
        end_date: this.endDate,
      },
      replaceUrl: true,
    });
  }

  load(): void {
    if (!this.workspaceId) return;
    this.loading = true;
    this.error = '';
    this.api
      .getJobs(
        this.workspaceId,
        this.startDate,
        this.endDate,
        this.environmentSelection.getSelectedId(),
        this.environmentSelection.getSelectedConnectionId()
      )
      .subscribe({
      next: (list) => {
        this.jobs = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = err?.message || 'Failed to load jobs';
        this.loading = false;
      },
    });
  }

  get filteredJobs(): JobSummary[] {
    const q = (this.filterText || '').toLowerCase().trim();
    if (!q) return this.jobs;
    return this.jobs.filter(
      (j) =>
        (j.job_id || '').toLowerCase().includes(q) ||
        (j.job_name || '').toLowerCase().includes(q) ||
        (j.job_type || '').toLowerCase().includes(q)
    );
  }

  openDetail(j: JobSummary): void {
    if (!this.workspaceId) return;
    this.router.navigate(['/app/jobs', this.workspaceId, j.job_id], {
      queryParams: { start_date: this.startDate, end_date: this.endDate },
    });
  }
}
