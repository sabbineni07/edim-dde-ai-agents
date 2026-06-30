import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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
import { ErrorAlertComponent } from '../../shared/error-alert/error-alert.component';

@Component({
  selector: 'app-datasets',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    PageHeaderComponent,
    EmptyStateComponent,
    LoadingCardComponent,
    StatusBadgeComponent,
    ErrorAlertComponent,
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
  formError = '';
  saving = false;

  pendingDelete: EnvironmentDataset | null = null;
  deleting = false;

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

  get formTitle(): string {
    return this.editingId ? 'Edit dataset' : 'New dataset';
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
    this.formError = '';
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
    this.formError = '';
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
    this.formError = '';
  }

  confirmDelete(d: EnvironmentDataset): void {
    this.pendingDelete = d;
  }

  cancelDelete(): void {
    this.pendingDelete = null;
    this.deleting = false;
  }

  onSchemaProfileChange(): void {
    const allowed = this.allowedSourceTypes();
    if (!allowed.includes(this.formSourceType)) {
      this.formSourceType = allowed[0] as 'databricks_delta' | 'local_csv';
    }
  }

  validateForm(): string | null {
    if (!this.formName.trim()) {
      return 'Name is required.';
    }
    if (this.formSourceType === 'databricks_delta' && !this.formTableFqn.trim()) {
      return 'Table FQN is required for Databricks Delta datasets.';
    }
    if (this.formSourceType === 'local_csv' && !this.formLocalPath.trim()) {
      return 'CSV path is required for local datasets.';
    }
    return null;
  }

  save(): void {
    if (!this.environmentId) {
      this.formError = 'Select an environment first.';
      return;
    }
    const validationError = this.validateForm();
    if (validationError) {
      this.formError = validationError;
      return;
    }
    this.saving = true;
    this.formError = '';

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
            this.environmentSelection.loadEnvironments().subscribe();
          },
          error: (err) => {
            this.saving = false;
            this.formError = parseApiError(err, 'Save failed');
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
          this.environmentSelection.loadEnvironments().subscribe();
        },
        error: (err) => {
          this.saving = false;
          this.formError = parseApiError(err, 'Create failed');
        },
      });
  }

  setDefault(d: EnvironmentDataset): void {
    if (!this.isAdmin) return;
    this.api.setDefaultEnvironmentDataset(this.environmentId, d.id).subscribe({
      next: () => {
        this.toast.success(`"${d.name}" set as default.`);
        this.loadDatasets();
        this.environmentSelection.loadEnvironments().subscribe();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to set default');
      },
    });
  }

  deleteDataset(): void {
    const d = this.pendingDelete;
    if (!this.isAdmin || !d) return;
    this.deleting = true;
    this.api.deleteEnvironmentDataset(this.environmentId, d.id).subscribe({
      next: () => {
        this.deleting = false;
        this.pendingDelete = null;
        this.toast.success('Dataset deleted.');
        this.loadDatasets();
        this.environmentSelection.loadEnvironments().subscribe();
      },
      error: (err) => {
        this.deleting = false;
        this.error = parseApiError(err, 'Delete failed');
        this.pendingDelete = null;
      },
    });
  }
}
