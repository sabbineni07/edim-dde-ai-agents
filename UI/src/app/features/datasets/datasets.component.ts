import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import {
  ApiService,
  EnvironmentDataset,
  SchemaProfileMeta,
} from '../../services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-datasets',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    LoadingCardComponent,
    StatusBadgeComponent,
  ],
  templateUrl: './datasets.component.html',
  styleUrls: ['./datasets.component.css'],
})
export class DatasetsComponent implements OnInit, OnDestroy {
  environmentId = '';
  environmentName = '';
  datasets: EnvironmentDataset[] = [];
  schemaProfiles: SchemaProfileMeta[] = [];
  loading = true;
  error = '';

  showForm = false;
  editingId: string | null = null;
  formName = '';
  formDescription = '';
  formSourceType: 'databricks_delta' | 'local_csv' = 'databricks_delta';
  formSchemaProfile = 'job_cluster_metrics';
  formTableFqn = '';
  formLocalPath = '';
  formSetDefault = false;
  saving = false;
  private subs = new Subscription();

  constructor(
    private api: ApiService,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private toast: ToastService
  ) {}

  get isAdmin(): boolean {
    return this.auth.isAdmin();
  }

  ngOnInit(): void {
    this.api.getSchemaProfiles().subscribe({
      next: (res) => {
        this.schemaProfiles = res.schema_profiles || [];
      },
    });

    this.subs.add(
      this.environmentSelection.watchSelectedId().subscribe((envId) => {
        if (!envId) {
          this.environmentId = '';
          this.environmentName = '';
          this.datasets = [];
          this.loading = false;
          return;
        }
        const sel = this.environmentSelection.getSelected();
        this.environmentId = envId;
        this.environmentName = sel?.displayName || envId;
        if (envId === 'local') {
          this.formSourceType = 'local_csv';
        } else {
          this.formSourceType = 'databricks_delta';
        }
        this.loadDatasets();
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  loadDatasets(): void {
    if (!this.environmentId) {
      this.datasets = [];
      this.loading = false;
      return;
    }
    this.loading = true;
    this.error = '';
    this.api.getEnvironmentDatasets(this.environmentId).subscribe({
      next: (list) => {
        this.datasets = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load datasets');
        this.loading = false;
      },
    });
  }

  profileLabel(profile: string): string {
    return this.schemaProfiles.find((p) => p.schema_profile === profile)?.label || profile;
  }

  sourceTypeLabel(type: string): string {
    return type === 'local_csv' ? 'Local CSV' : 'Databricks Delta';
  }

  datasetRef(d: EnvironmentDataset): string {
    return d.table_ref || d.table_fqn || d.local_path || '—';
  }

  allowedSourceTypes(): string[] {
    const profile = this.schemaProfiles.find((p) => p.schema_profile === this.formSchemaProfile);
    return profile?.source_types?.length
      ? profile.source_types
      : ['databricks_delta', 'local_csv'];
  }

  startCreate(): void {
    this.showForm = true;
    this.editingId = null;
    this.formName = '';
    this.formDescription = '';
    this.formSchemaProfile = 'job_cluster_metrics';
    this.formSourceType = this.environmentId === 'local' ? 'local_csv' : 'databricks_delta';
    this.formTableFqn = '';
    this.formLocalPath = '';
    this.formSetDefault = false;
    this.error = '';
  }

  startEdit(d: EnvironmentDataset): void {
    this.showForm = true;
    this.editingId = d.id;
    this.formName = d.name;
    this.formDescription = d.description || '';
    this.formSourceType = d.source_type;
    this.formSchemaProfile = d.schema_profile;
    this.formTableFqn = d.table_fqn || '';
    this.formLocalPath = d.local_path || '';
    this.formSetDefault = d.is_default;
    this.error = '';
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  onSchemaProfileChange(): void {
    const allowed = this.allowedSourceTypes();
    if (!allowed.includes(this.formSourceType)) {
      this.formSourceType = allowed[0] as 'databricks_delta' | 'local_csv';
    }
  }

  save(): void {
    if (!this.environmentId || !this.formName.trim()) {
      this.error = 'Name and environment are required.';
      return;
    }
    this.saving = true;
    this.error = '';

    if (this.editingId) {
      this.api
        .updateEnvironmentDataset(this.environmentId, this.editingId, {
          name: this.formName.trim(),
          description: this.formDescription.trim() || undefined,
          table_fqn: this.formSourceType === 'databricks_delta' ? this.formTableFqn.trim() : undefined,
          local_path: this.formSourceType === 'local_csv' ? this.formLocalPath.trim() : undefined,
        })
        .subscribe({
          next: () => {
            this.saving = false;
            this.showForm = false;
            this.toast.success('Dataset updated.');
            this.loadDatasets();
          },
          error: (err) => {
            this.saving = false;
            this.error = parseApiError(err, 'Save failed');
          },
        });
      return;
    }

    this.api
      .createEnvironmentDataset(this.environmentId, {
        name: this.formName.trim(),
        description: this.formDescription.trim() || undefined,
        source_type: this.formSourceType,
        schema_profile: this.formSchemaProfile,
        table_fqn: this.formSourceType === 'databricks_delta' ? this.formTableFqn.trim() : undefined,
        local_path: this.formSourceType === 'local_csv' ? this.formLocalPath.trim() : undefined,
        set_default: this.formSetDefault,
      })
      .subscribe({
        next: () => {
          this.saving = false;
          this.showForm = false;
          this.toast.success('Dataset created.');
          this.loadDatasets();
        },
        error: (err) => {
          this.saving = false;
          this.error = parseApiError(err, 'Create failed');
        },
      });
  }

  setDefault(d: EnvironmentDataset): void {
    if (!this.isAdmin) return;
    this.api.setDefaultEnvironmentDataset(this.environmentId, d.id).subscribe({
      next: () => {
        this.toast.success(`"${d.name}" set as default.`);
        this.loadDatasets();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to set default');
      },
    });
  }

  deleteDataset(d: EnvironmentDataset): void {
    if (!this.isAdmin || !confirm(`Delete dataset "${d.name}"?`)) return;
    this.api.deleteEnvironmentDataset(this.environmentId, d.id).subscribe({
      next: () => {
        this.toast.success('Dataset deleted.');
        this.loadDatasets();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Delete failed');
      },
    });
  }
}
