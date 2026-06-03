import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService, Workspace } from '../../services/api.service';
import { last30DaysDateStrings } from '../../core/date-range.util';

@Component({
  selector: 'app-workspaces',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './workspaces.component.html',
  styleUrls: ['./workspaces.component.css'],
})
export class WorkspacesComponent implements OnInit {
  workspaces: Workspace[] = [];
  loading = true;
  error = '';
  /** YYYY-MM-DD — passed as `start_date` / `end_date` query params on API and navigation */
  startDate = '';
  endDate = '';

  constructor(
    private api: ApiService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((qp) => {
      const start = qp.get('start_date')?.trim();
      const end = qp.get('end_date')?.trim();
      if (start && end) {
        this.startDate = start;
        this.endDate = end;
      } else {
        const r = last30DaysDateStrings();
        this.startDate = r.startDate;
        this.endDate = r.endDate;
      }
      this.load();
    });
  }

  /** Writes `start_date` / `end_date` to the URL (bookmarkable) and reloads via query subscription. */
  applyDateRangeToUrl(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { start_date: this.startDate, end_date: this.endDate },
      replaceUrl: true,
    });
  }

  load(): void {
    this.loading = true;
    this.error = '';
    this.api.getWorkspaces(this.startDate, this.endDate).subscribe({
      next: (list) => {
        this.workspaces = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = err?.message || 'Failed to load workspaces';
        this.loading = false;
      },
    });
  }

  openJobs(w: Workspace): void {
    this.router.navigate(['/app/jobs'], {
      queryParams: {
        workspaceId: w.workspace_id,
        start_date: this.startDate,
        end_date: this.endDate,
      },
    });
  }

  openWorkspaceSetup(w: Workspace): void {
    this.router.navigate(['/app/workspaces', w.workspace_id], {
      queryParams: { tab: 'connections' },
    });
  }
}
