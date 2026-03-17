import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApiService, Workspace } from '../../services/api.service';

@Component({
  selector: 'app-workspaces',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './workspaces.component.html',
  styleUrls: ['./workspaces.component.css'],
})
export class WorkspacesComponent implements OnInit {
  workspaces: Workspace[] = [];
  loading = true;
  error = '';

  constructor(
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = '';
    this.api.getWorkspaces().subscribe({
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
    this.router.navigate(['/app/jobs'], { queryParams: { workspaceId: w.workspace_id } });
  }
}
