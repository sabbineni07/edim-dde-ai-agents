import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import {
  ApiService,
  ConnectionTypeMeta,
  EnvironmentConnection,
} from '../../services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { EnvironmentConnectionCacheService } from '../../core/services/environment-connection-cache.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import { ToastService } from '../../core/services/toast.service';
import { ErrorAlertComponent } from '../../shared/error-alert/error-alert.component';

@Component({
  selector: 'app-connections',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    LoadingCardComponent,
    StatusBadgeComponent,
    ErrorAlertComponent,
  ],
  templateUrl: './connections.component.html',
  styleUrls: ['./connections.component.css'],
})
export class ConnectionsComponent implements OnInit, OnDestroy {
  environmentId = '';
  environmentName = '';
  defaultDatasetName = '';
  defaultDatasetRef = '';
  connections: EnvironmentConnection[] = [];
  connectionTypes: ConnectionTypeMeta[] = [];
  loading = true;
  error = '';

  showForm = false;
  editingId: string | null = null;
  formName = '';
  formType = 'databricks';
  formConfig: Record<string, string> = {};
  formSetDefault = false;
  formError = '';
  saving = false;

  pendingDelete: EnvironmentConnection | null = null;
  deleting = false;

  private subs = new Subscription();

  constructor(
    private api: ApiService,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService,
    private toast: ToastService
  ) {}

  get isAdmin(): boolean {
    return this.auth.isAdmin();
  }

  get formTitle(): string {
    return this.editingId ? 'Edit connection' : 'New connection';
  }

  ngOnInit(): void {
    this.api.getConnectionTypes().subscribe({
      next: (res) => {
        this.connectionTypes = res.connection_types || [];
      },
    });

    this.subs.add(
      this.environmentSelection.watchEnvironments().subscribe(() => {
        if (this.environmentId) {
          this.syncEnvContext(this.environmentId);
        }
      })
    );

    this.subs.add(
      this.environmentSelection.watchSelectedId().subscribe((envId) => {
        if (!envId) {
          this.environmentId = '';
          this.environmentName = '';
          this.defaultDatasetName = '';
          this.defaultDatasetRef = '';
          this.connections = [];
          this.loading = false;
          return;
        }
        const sel = this.environmentSelection.getSelected();
        this.environmentId = envId;
        this.environmentName = sel?.displayName || envId;
        this.syncEnvContext(envId);
        this.loadConnections();
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  private syncEnvContext(envId: string): void {
    const env = this.environmentSelection.getEnvironmentRecord(envId);
    this.defaultDatasetName = env?.default_dataset_name?.trim() || '';
    this.defaultDatasetRef = env?.default_dataset_ref?.trim() || '';
  }

  loadConnections(force = false): void {
    if (!this.environmentId) {
      this.connections = [];
      this.loading = false;
      return;
    }
    this.loading = true;
    this.error = '';
    this.connectionCache.getConnections(this.environmentId, force).subscribe({
      next: (list) => {
        this.connections = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load connections');
        this.loading = false;
      },
    });
  }

  typeLabel(type: string): string {
    return this.typeMeta(type)?.label || type;
  }

  typeMeta(type: string): ConnectionTypeMeta | undefined {
    return this.connectionTypes.find((t) => t.connection_type === type);
  }

  startCreate(): void {
    this.showForm = true;
    this.editingId = null;
    this.formName = '';
    this.formType = 'databricks';
    this.formConfig = {};
    this.formSetDefault = false;
    this.formError = '';
  }

  startEdit(c: EnvironmentConnection): void {
    this.showForm = true;
    this.editingId = c.id;
    this.formName = c.name;
    this.formType = c.connection_type;
    this.formConfig = {};
    const meta = this.typeMeta(c.connection_type);
    for (const f of meta?.fields || []) {
      const v = c.config[f.key];
      if (v != null) this.formConfig[f.key] = String(v);
    }
    this.formSetDefault = c.is_default;
    this.formError = '';
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
    this.formError = '';
  }

  confirmDelete(c: EnvironmentConnection): void {
    this.pendingDelete = c;
  }

  cancelDelete(): void {
    this.pendingDelete = null;
    this.deleting = false;
  }

  buildConfig(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    const meta = this.typeMeta(this.formType);
    for (const f of meta?.fields || []) {
      let v = this.formConfig[f.key]?.trim();
      if (!v && (f as { default?: string }).default) {
        v = String((f as { default?: string }).default);
      }
      if (v) out[f.key] = v;
    }
    return out;
  }

  validateForm(): string | null {
    if (!this.formName.trim()) {
      return 'Name is required.';
    }
    const meta = this.typeMeta(this.formType);
    for (const f of meta?.fields || []) {
      let v = this.formConfig[f.key]?.trim();
      if (!v && f.default) v = String(f.default);
      if (f.required && !v) {
        return `${f.label} is required.`;
      }
    }
    return null;
  }

  private afterMutation(): void {
    this.environmentSelection.invalidateConnectionCache(this.environmentId);
    this.loadConnections(true);
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
    const config = this.buildConfig();
    if (this.editingId) {
      this.api
        .updateEnvironmentConnection(this.environmentId, this.editingId, {
          name: this.formName.trim(),
          config,
        })
        .subscribe({
          next: () => {
            this.saving = false;
            this.showForm = false;
            this.toast.success('Connection updated.');
            this.afterMutation();
          },
          error: (err) => {
            this.saving = false;
            this.formError = parseApiError(err, 'Save failed');
          },
        });
      return;
    }
    this.api
      .createEnvironmentConnection(this.environmentId, {
        name: this.formName.trim(),
        connection_type: this.formType,
        config,
        set_default: this.formSetDefault,
      })
      .subscribe({
        next: () => {
          this.saving = false;
          this.showForm = false;
          this.toast.success('Connection created.');
          this.afterMutation();
        },
        error: (err) => {
          this.saving = false;
          this.formError = parseApiError(err, 'Create failed');
        },
      });
  }

  setDefault(c: EnvironmentConnection): void {
    if (!this.isAdmin) return;
    this.api.setDefaultEnvironmentConnection(this.environmentId, c.id).subscribe({
      next: () => {
        this.toast.success(`"${c.name}" set as default.`);
        this.afterMutation();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to set default');
      },
    });
  }

  deleteConnection(): void {
    const c = this.pendingDelete;
    if (!this.isAdmin || !c) return;
    this.deleting = true;
    this.api.deleteEnvironmentConnection(this.environmentId, c.id).subscribe({
      next: () => {
        this.deleting = false;
        this.pendingDelete = null;
        this.toast.success('Connection deleted.');
        if (this.environmentSelection.getSelectedConnectionId() === c.id) {
          this.environmentSelection.setSelectedConnection(null);
        }
        this.afterMutation();
      },
      error: (err) => {
        this.deleting = false;
        this.error = parseApiError(err, 'Delete failed');
        this.pendingDelete = null;
      },
    });
  }
}
