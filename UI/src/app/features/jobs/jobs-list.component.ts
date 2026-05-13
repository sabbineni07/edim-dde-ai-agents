import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, JobSummary } from '../../services/api.service';
import { last30DaysDateStrings } from '../../core/date-range.util';

@Component({
  selector: 'app-jobs-list',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './jobs-list.component.html',
  styleUrls: ['./jobs-list.component.css'],
})
export class JobsListComponent implements OnInit {
  workspaceId: string | null = null;
  startDate = '';
  endDate = '';
  jobs: JobSummary[] = [];
  loading = true;
  error = '';
  filterText = '';

  constructor(
    private api: ApiService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    this.route.queryParams.subscribe((qp) => {
      this.workspaceId = qp['workspaceId'] ?? null;
      const s = typeof qp['start_date'] === 'string' ? qp['start_date'].trim() : '';
      const e = typeof qp['end_date'] === 'string' ? qp['end_date'].trim() : '';
      const fallback = last30DaysDateStrings();
      this.startDate = s || fallback.startDate;
      this.endDate = e || fallback.endDate;
      if (this.workspaceId) this.load();
      else {
        this.loading = false;
        this.jobs = [];
      }
    });
  }

  load(): void {
    if (!this.workspaceId) return;
    this.loading = true;
    this.error = '';
    this.api.getJobs(this.workspaceId, this.startDate, this.endDate).subscribe({
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
        (j.workload_type || '').toLowerCase().includes(q)
    );
  }

  openDetail(j: JobSummary): void {
    if (!this.workspaceId) return;
    this.router.navigate(['/app/jobs', this.workspaceId, j.job_id], {
      queryParams: { start_date: this.startDate, end_date: this.endDate },
    });
  }
}
