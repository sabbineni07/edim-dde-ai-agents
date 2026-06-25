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

@Component({
  selector: 'app-connections',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './connections.component.html',
  styleUrls: ['./connections.component.css'],
})
export class ConnectionsComponent implements OnInit, OnDestroy {
  environmentId = '';
  environmentName = '';
  metricsTableFqn = '';
  connections: EnvironmentConnection[] = [];
  connectionTypes: ConnectionTypeMeta[] = [];
  loading = true;
  error = '';
  message = '';

  showForm = false;
  editingId: string | null = null;
  formName = '';
  formType = 'databricks';
  formConfig: Record<string, string> = {};
  formSetDefault = false;
  saving = false;
  private subs = new Subscription();

  constructor(
    private api: ApiService,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService
  ) {}

  get isAdmin(): boolean {
    return this.auth.isAdmin();
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
          const env = this.environmentSelection.getEnvironmentRecord(this.environmentId);
          this.metricsTableFqn = env?.table_fqn?.trim() || '';
        }
      })
    );

    this.subs.add(
      this.environmentSelection.watchSelectedId().subscribe((envId) => {
        if (!envId) {
          this.environmentId = '';
          this.environmentName = '';
          this.connections = [];
          this.loading = false;
          return;
        }
        const sel = this.environmentSelection.getSelected();
        this.environmentId = envId;
        this.environmentName = sel?.displayName || envId;
        const env = this.environmentSelection.getEnvironmentRecord(envId);
        this.metricsTableFqn = env?.table_fqn?.trim() || '';
        this.loadConnections();
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  /** Use cache unless force refresh (Refresh button or after CRUD). */
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
    this.message = '';
    this.error = '';
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
    this.message = '';
    this.error = '';
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  buildConfig(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    const meta = this.typeMeta(this.formType);
    for (const f of meta?.fields || []) {
      const v = this.formConfig[f.key]?.trim();
      if (v) out[f.key] = v;
    }
    return out;
  }

  private afterMutation(): void {
    this.environmentSelection.invalidateConnectionCache(this.environmentId);
    this.loadConnections(true);
  }

  save(): void {
    if (!this.environmentId || !this.formName.trim()) {
      this.error = 'Name and environment are required.';
      return;
    }
    this.saving = true;
    this.error = '';
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
            this.message = 'Connection updated.';
            this.afterMutation();
          },
          error: (err) => {
            this.saving = false;
            this.error = parseApiError(err, 'Save failed');
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
          this.message = 'Connection created.';
          this.afterMutation();
        },
        error: (err) => {
          this.saving = false;
          this.error = parseApiError(err, 'Create failed');
        },
      });
  }

  setDefault(c: EnvironmentConnection): void {
    if (!this.isAdmin) return;
    this.api.setDefaultEnvironmentConnection(this.environmentId, c.id).subscribe({
      next: () => {
        this.message = `"${c.name}" set as default.`;
        this.afterMutation();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to set default');
      },
    });
  }

  deleteConnection(c: EnvironmentConnection): void {
    if (!this.isAdmin || !confirm(`Delete connection "${c.name}"?`)) return;
    this.api.deleteEnvironmentConnection(this.environmentId, c.id).subscribe({
      next: () => {
        this.message = 'Connection deleted.';
        if (this.environmentSelection.getSelectedConnectionId() === c.id) {
          this.environmentSelection.setSelectedConnection(null);
        }
        this.afterMutation();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Delete failed');
      },
    });
  }
}
