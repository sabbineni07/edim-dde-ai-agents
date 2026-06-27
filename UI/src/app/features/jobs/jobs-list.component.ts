import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, JobSummary, UiHints, Workspace } from '../../services/api.service';
import {
  daysBetween,
  defaultBrowseDateRange,
} from '../../core/date-range.util';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { BrowseDataCacheService } from '../../core/services/browse-data-cache.service';

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
  readonly pageSizeOptions = [10, 25, 50, 100];
  pageSize = 25;
  currentPage = 1;
  private forceNextLoad = false;

  constructor(
    private api: ApiService,
    private router: Router,
    private route: ActivatedRoute,
    private workspaceSelection: WorkspaceSelectionService,
    private environmentSelection: EnvironmentSelectionService,
    private browseCache: BrowseDataCacheService
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

  private loadWorkspaces(force = false): void {
    const envId = this.environmentSelection.getSelectedId();
    const connId = this.environmentSelection.getSelectedConnectionId();
    const datasetId = this.environmentSelection.getSelectedDatasetId();
    if (!envId) {
      this.workspaces = [];
      this.workspacesLoading = false;
      return;
    }

    const cacheKey = this.browseCache.workspacesKey(envId, connId, datasetId);
    const cached = !force && this.browseCache.peek<Workspace[]>(cacheKey);
    this.workspacesLoading = !cached;
    if (cached) {
      this.workspaces = cached;
      this.syncFromQueryParams(this.route.snapshot.queryParams);
      return;
    }

    this.browseCache
      .get(cacheKey, () => this.api.browseWorkspaces(envId, connId, datasetId), force)
      .subscribe({
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
    const force = this.forceNextLoad;
    this.forceNextLoad = false;
    this.load(force);
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
    return defaultBrowseDateRange(this.uiHints);
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
    this.forceNextLoad = true;
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

  refreshJobs(): void {
    if (!this.workspaceId) return;
    this.forceNextLoad = true;
    this.load(true);
  }

  load(force = false): void {
    if (!this.workspaceId) return;
    const envId = this.environmentSelection.getSelectedId();
    const connId = this.environmentSelection.getSelectedConnectionId();
    const datasetId = this.environmentSelection.getSelectedDatasetId();
    const cacheKey = this.browseCache.jobsKey(
      envId,
      connId,
      datasetId,
      this.workspaceId,
      this.startDate,
      this.endDate
    );
    const cached = !force && this.browseCache.peek<JobSummary[]>(cacheKey);
    this.loading = !cached;
    this.error = '';
    if (!force) {
      this.currentPage = 1;
    }
    if (!cached) {
      this.jobs = [];
    }

    this.browseCache
      .get(
        cacheKey,
        () =>
          this.api.getJobs(
            this.workspaceId!,
            this.startDate,
            this.endDate,
            envId,
            connId,
            datasetId
          ),
        force
      )
      .subscribe({
        next: (list) => {
          this.jobs = list;
          this.loading = false;
          this.clampCurrentPage();
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

  get totalFilteredJobs(): number {
    return this.filteredJobs.length;
  }

  get totalPages(): number {
    if (this.totalFilteredJobs === 0) return 1;
    return Math.ceil(this.totalFilteredJobs / this.pageSize);
  }

  get paginatedJobs(): JobSummary[] {
    const start = (this.currentPage - 1) * this.pageSize;
    return this.filteredJobs.slice(start, start + this.pageSize);
  }

  get pageRangeStart(): number {
    if (this.totalFilteredJobs === 0) return 0;
    return (this.currentPage - 1) * this.pageSize + 1;
  }

  get pageRangeEnd(): number {
    return Math.min(this.currentPage * this.pageSize, this.totalFilteredJobs);
  }

  onFilterChange(): void {
    this.currentPage = 1;
    this.clampCurrentPage();
  }

  onPageSizeChange(): void {
    this.currentPage = 1;
    this.clampCurrentPage();
  }

  goToPage(page: number): void {
    const next = Math.min(Math.max(1, page), this.totalPages);
    if (next !== this.currentPage) {
      this.currentPage = next;
    }
  }

  goToFirstPage(): void {
    this.goToPage(1);
  }

  goToLastPage(): void {
    this.goToPage(this.totalPages);
  }

  get visiblePageNumbers(): number[] {
    const total = this.totalPages;
    if (total <= 1) {
      return total === 1 ? [1] : [];
    }
    const windowSize = 5;
    let start = Math.max(1, this.currentPage - Math.floor(windowSize / 2));
    let end = Math.min(total, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }

  private clampCurrentPage(): void {
    if (this.currentPage > this.totalPages) {
      this.currentPage = this.totalPages;
    }
    if (this.currentPage < 1) {
      this.currentPage = 1;
    }
  }

  openDetail(j: JobSummary): void {
    if (!this.workspaceId) return;
    this.router.navigate(['/app/jobs', this.workspaceId, j.job_id], {
      queryParams: { start_date: this.startDate, end_date: this.endDate },
    });
  }
}
