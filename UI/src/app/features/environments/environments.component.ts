import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  LocalDatasetInfo,
  PlatformEnvironment,
  PlatformEnvironmentUpdate,
} from '../../services/api.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { AuthService } from '../../core/services/auth.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';

@Component({
  selector: 'app-environments',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PageHeaderComponent, LoadingCardComponent],
  templateUrl: './environments.component.html',
  styleUrls: ['./environments.component.css'],
})
export class EnvironmentsComponent implements OnInit {
  environments: PlatformEnvironment[] = [];
  loading = true;
  error = '';

  /** Local CSV panel */
  localExpanded = false;
  localDataset: LocalDatasetInfo | null = null;
  uploadInProgress = false;
  uploadError = '';
  uploadSuccess = '';
  selectedFile: File | null = null;

  /** Admin edit */
  editing: PlatformEnvironment | null = null;
  editForm: PlatformEnvironmentUpdate = {};
  editSaving = false;
  editError = '';

  constructor(
    private api: ApiService,
    private router: Router,
    private environmentSelection: EnvironmentSelectionService,
    private auth: AuthService
  ) {}

  get isAdmin(): boolean {
    return this.auth.isAdmin();
  }

  ngOnInit(): void {
    this.api.getUiHints().subscribe({
      next: (hints) => {
        if (hints.admin_usernames?.length) {
          this.auth.setAdminUsernames(hints.admin_usernames);
        }
      },
    });
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = '';
    this.api.getEnvironments().subscribe({
      next: (list) => {
        this.environments = list;
        const local = list.find((e) => e.id === 'local');
        this.localDataset = local?.local_dataset ?? null;
        this.loading = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load environments');
        this.loading = false;
      },
    });
  }

  tierBadgeClass(tier: string): string {
    const t = (tier || '').toUpperCase();
    if (t === 'DEV') return 'bg-primary';
    if (t === 'UAT') return 'bg-info text-dark';
    if (t === 'INTG') return 'bg-secondary';
    if (t === 'PROD') return 'bg-danger';
    if (t === 'SDBX') return 'bg-warning text-dark';
    if (t === 'LOCAL') return 'bg-success';
    return 'bg-light text-dark';
  }

  readinessLabel(env: PlatformEnvironment): string {
    if (env.readiness === 'ready') return 'Ready';
    if (env.readiness === 'needs_connection') return 'Needs connection';
    if (env.readiness === 'needs_upload') return 'Needs CSV';
    return 'Unknown';
  }

  canOpen(env: PlatformEnvironment): boolean {
    if (env.id === 'local') return env.readiness === 'ready';
    return env.readiness === 'ready';
  }

  openEnvironment(env: PlatformEnvironment): void {
    if (!this.canOpen(env) && env.id !== 'local') {
      if (this.isAdmin) {
        this.openEdit(env);
      }
      return;
    }
    if (env.id === 'local' && !this.canOpen(env)) {
      this.localExpanded = true;
      return;
    }
    this.environmentSelection.setSelected({
      id: env.id,
      displayName: env.display_name,
    });
    this.router.navigate(['/app/workspaces']);
  }

  openEdit(env: PlatformEnvironment): void {
    this.editing = env;
    this.editError = '';
    this.editForm = {
      display_name: env.display_name,
      description: env.description,
      environment_tier: env.environment_tier,
      sort_order: env.sort_order,
      icon: env.icon,
      is_enabled: env.is_enabled !== false,
    };
  }

  closeEdit(): void {
    this.editing = null;
    this.editError = '';
  }

  saveEdit(): void {
    if (!this.editing) return;
    this.editSaving = true;
    this.editError = '';
    this.api.updateEnvironment(this.editing.id, this.editForm).subscribe({
      next: () => {
        this.editSaving = false;
        this.closeEdit();
        this.load();
      },
      error: (err) => {
        this.editSaving = false;
        this.editError = parseApiError(err, 'Save failed');
      },
    });
  }

  toggleLocalPanel(): void {
    this.localExpanded = !this.localExpanded;
    if (this.localExpanded) {
      this.refreshLocalDataset();
    }
  }

  refreshLocalDataset(): void {
    this.api.getLocalDataset().subscribe({
      next: (info) => {
        this.localDataset = info;
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
    this.uploadError = '';
    this.uploadSuccess = '';
  }

  downloadTemplate(): void {
    this.api.downloadLocalTemplate();
  }

  uploadCsv(): void {
    if (!this.selectedFile) {
      this.uploadError = 'Choose a CSV file first.';
      return;
    }
    this.uploadInProgress = true;
    this.uploadError = '';
    this.uploadSuccess = '';
    this.api.uploadLocalCsv(this.selectedFile).subscribe({
      next: (info) => {
        this.localDataset = info;
        this.uploadInProgress = false;
        this.uploadSuccess = `Uploaded ${info.filename} (${info.row_count ?? '?'} rows).`;
        this.selectedFile = null;
        this.load();
      },
      error: (err) => {
        this.uploadInProgress = false;
        this.uploadError = parseApiError(err, 'Upload failed');
      },
    });
  }

  resetToSample(): void {
    this.uploadInProgress = true;
    this.uploadError = '';
    this.api.resetLocalDataset().subscribe({
      next: (info) => {
        this.localDataset = info;
        this.uploadInProgress = false;
        this.uploadSuccess = 'Reverted to bundled sample CSV.';
        this.load();
      },
      error: (err) => {
        this.uploadInProgress = false;
        this.uploadError = parseApiError(err, 'Reset failed');
      },
    });
  }

  openLocalAfterUpload(): void {
    this.environmentSelection.setSelected({
      id: 'local',
      displayName: 'Local (sample CSV)',
    });
    this.router.navigate(['/app/workspaces']);
  }
}
