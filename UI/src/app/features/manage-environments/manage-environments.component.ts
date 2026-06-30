import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  PlatformEnvironment,
  PlatformEnvironmentUpdate,
} from '../../services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';

@Component({
  selector: 'app-manage-environments',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PageHeaderComponent, LoadingCardComponent],
  templateUrl: './manage-environments.component.html',
  styleUrls: ['./manage-environments.component.css'],
})
export class ManageEnvironmentsComponent implements OnInit {
  readonly tierOptions = ['DEV', 'UAT', 'INTG', 'PROD', 'SDBX', 'LOCAL'];
  readonly iconOptions = [
    'code-slash',
    'check2-circle',
    'diagram-3',
    'shield-check',
    'box-seam',
    'file-earmark-spreadsheet',
    'cloud',
    'layers',
    'database',
    'server',
    'hdd-stack',
    'cpu',
    'graph-up',
    'gear',
  ];

  environments: PlatformEnvironment[] = [];
  loading = true;
  error = '';
  editing: PlatformEnvironment | null = null;
  editForm: PlatformEnvironmentUpdate = {};
  saving = false;
  saveError = '';

  constructor(
    private api: ApiService,
    private auth: AuthService,
    private router: Router,
    private environmentSelection: EnvironmentSelectionService
  ) {}

  ngOnInit(): void {
    if (!this.auth.isAdmin()) {
      void this.router.navigate(['/app/workspaces']);
      return;
    }
    this.load();
  }

  get tierOptionsForEdit(): string[] {
    const current = (this.editForm.environment_tier || this.editing?.environment_tier || '').trim();
    if (current && !this.tierOptions.includes(current)) {
      return [current, ...this.tierOptions];
    }
    return this.tierOptions;
  }

  get canSave(): boolean {
    return Boolean(this.editForm.display_name?.trim());
  }

  load(): void {
    this.loading = true;
    this.api.getEnvironments().subscribe({
      next: (list) => {
        this.environments = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load environments');
        this.loading = false;
      },
    });
  }

  tierBadgeClass(tier: string | undefined): string {
    const t = (tier || '').toUpperCase();
    if (t === 'DEV') return 'bg-primary';
    if (t === 'UAT') return 'bg-info text-dark';
    if (t === 'INTG') return 'bg-secondary';
    if (t === 'PROD') return 'bg-danger';
    if (t === 'SDBX') return 'bg-warning text-dark';
    if (t === 'LOCAL') return 'bg-success';
    return 'bg-light text-dark';
  }

  connectionCount(env: PlatformEnvironment): number {
    return env.connection_count ?? env.metrics_connection_count ?? 0;
  }

  datasetCount(env: PlatformEnvironment): number {
    return env.metrics_dataset_count ?? 0;
  }

  setupSummary(env: PlatformEnvironment): string {
    const conns = this.connectionCount(env);
    const datasets = this.datasetCount(env);
    const connWord = conns === 1 ? 'connection' : 'connections';
    const dsWord = datasets === 1 ? 'dataset' : 'datasets';
    return `${conns} ${connWord} · ${datasets} ${dsWord}`;
  }

  setupStatusLabel(env: PlatformEnvironment): string {
    if (env.readiness === 'ready') return 'Ready';
    if (env.readiness === 'needs_connection') return 'Needs setup';
    if (env.readiness === 'needs_upload') return 'Needs CSV';
    return 'Unknown';
  }

  setupStatusClass(env: PlatformEnvironment): string {
    if (env.readiness === 'ready') return 'bg-success';
    if (env.readiness === 'needs_connection') return 'bg-warning text-dark';
    if (env.readiness === 'needs_upload') return 'bg-secondary';
    return 'bg-light text-dark';
  }

  selectIcon(icon: string): void {
    this.editForm = { ...this.editForm, icon };
  }

  openConfigure(env: PlatformEnvironment, target: 'connections' | 'datasets'): void {
    this.environmentSelection.setSelected({
      id: env.id,
      displayName: env.display_name,
    });
    void this.router.navigate([`/app/${target}`]);
  }

  configureFromEdit(target: 'connections' | 'datasets'): void {
    if (!this.editing) return;
    this.openConfigure(this.editing, target);
    this.closeEdit();
  }

  openEdit(env: PlatformEnvironment): void {
    this.editing = env;
    this.saveError = '';
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
    this.saveError = '';
  }

  saveEdit(): void {
    if (!this.editing || !this.canSave) return;
    this.saving = true;
    this.saveError = '';
    this.api.updateEnvironment(this.editing.id, this.editForm).subscribe({
      next: () => {
        this.saving = false;
        this.closeEdit();
        this.load();
      },
      error: (err) => {
        this.saving = false;
        this.saveError = parseApiError(err, 'Save failed');
      },
    });
  }
}
