import { Component, DestroyRef, OnInit, inject, input } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  AgentConnectionManifest,
  AgentInfo,
  AgentRoleSpec,
  ApiService,
  ConnectionTypeMeta,
  EditableSettingsField,
  EnvironmentConnection,
  EnvironmentDataset,
  WorkspaceAgent,
} from '../../services/api.service';
import { parseApiError } from '../../core/api-error.util';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';

@Component({
  selector: 'app-workspace-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './workspace-detail.component.html',
  styleUrls: ['./workspace-detail.component.css'],
})
export class WorkspaceDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  workspaceId = input.required<string>();

  environmentId = '';
  environmentDisplayName = '';
  workspaceName = '';

  connectionTypes: ConnectionTypeMeta[] = [];
  envConnections: EnvironmentConnection[] = [];
  envDatasets: EnvironmentDataset[] = [];
  workspaceAgents: WorkspaceAgent[] = [];
  agentsCatalog: AgentInfo[] = [];

  loadingConnections = true;
  loadingAgents = true;
  saving = false;
  message = '';
  error = '';

  showAgentWizard = false;
  /** Set when editing an existing install; null when adding a new agent. */
  editingAgentId: string | null = null;
  wizardAgentId = '';
  wizardName = '';
  wizardBindings: Record<string, string> = {};
  wizardManifest: AgentConnectionManifest | null = null;
  wizardSettings: Record<string, string | number | boolean> = {};
  wizardEditableFields: EditableSettingsField[] = [];

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    private workspaceSelection: WorkspaceSelectionService,
    private environmentSelection: EnvironmentSelectionService
  ) {}

  ngOnInit(): void {
    this.environmentSelection
      .watchSelectedId()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((envId) => {
        this.environmentId = envId || '';
        const sel = this.environmentSelection.getSelected();
        this.environmentDisplayName = sel?.displayName || envId || '';
        this.refresh();
      });

    this.api.getConnectionTypes().subscribe({
      next: (res) => {
        this.connectionTypes = res.connection_types || [];
      },
    });
    this.api.getAgents().subscribe({
      next: (res) => {
        this.agentsCatalog = res.agents || [];
        this.applyDefaultWizardAgentId();
      },
    });
  }

  refresh(): void {
    const ws = this.workspaceId();
    this.loadingAgents = true;
    this.error = '';
    if (!this.environmentId) {
      this.envConnections = [];
      this.envDatasets = [];
      this.loadingConnections = false;
      this.loadingAgents = false;
      return;
    }
    this.loadingConnections = true;
    this.api.getEnvironmentConnections(this.environmentId).subscribe({
      next: (list) => {
        this.envConnections = list;
        this.loadingConnections = false;
      },
      error: () => {
        this.loadingConnections = false;
      },
    });
    this.api.getEnvironmentDatasets(this.environmentId).subscribe({
      next: (list) => {
        this.envDatasets = list;
      },
      error: () => {
        this.envDatasets = [];
      },
    });
    this.api.getWorkspaceAgents(ws).subscribe({
      next: (list) => {
        this.workspaceAgents = list;
        if (list.length && list[0].workspace_name) {
          this.workspaceName = list[0].workspace_name!;
        }
        this.loadingAgents = false;
      },
      error: () => {
        this.loadingAgents = false;
      },
    });
  }

  connectionTypeMeta(type: string): ConnectionTypeMeta | undefined {
    return this.connectionTypes.find((t) => t.connection_type === type);
  }

  connectionsForTypes(allowed: string[]): EnvironmentConnection[] {
    const set = new Set(allowed);
    return this.envConnections.filter((c) => set.has(c.connection_type));
  }

  roleSpec(role: string): AgentRoleSpec | null {
    const spec = this.wizardManifest?.roles[role];
    if (!spec || Array.isArray(spec)) return null;
    return spec;
  }

  isDatasetRole(role: string): boolean {
    return this.roleSpec(role)?.kind === 'dataset';
  }

  isConnectionRole(role: string): boolean {
    const spec = this.wizardManifest?.roles[role];
    if (!spec) return false;
    if (Array.isArray(spec)) return true;
    return spec.kind === 'connection';
  }

  datasetsForRole(role: string): EnvironmentDataset[] {
    const spec = this.roleSpec(role);
    const profile = spec?.schema_profile?.trim();
    if (!profile) return [];
    return this.envDatasets.filter((d) => d.schema_profile === profile);
  }

  datasetLabel(ds: EnvironmentDataset): string {
    const ref = ds.table_ref || ds.table_fqn || ds.local_path || '';
    return ref ? `${ds.name} (${ref})` : ds.name;
  }

  get isEditingAgent(): boolean {
    return !!this.editingAgentId;
  }

  startAddAgent(): void {
    this.showAgentWizard = true;
    this.editingAgentId = null;
    this.wizardAgentId = '';
    this.wizardName = '';
    this.wizardBindings = {};
    this.wizardSettings = {};
    this.wizardManifest = null;
    this.wizardEditableFields = [];
    this.error = '';
    this.message = '';
    this.applyDefaultWizardAgentId();
  }

  startEditAgent(wa: WorkspaceAgent): void {
    this.showAgentWizard = true;
    this.editingAgentId = wa.id;
    this.wizardAgentId = wa.agent_id;
    this.wizardName = wa.name;
    this.wizardBindings = { ...(wa.bindings || {}) };
    this.wizardSettings = this.normalizeWizardSettings(wa.agent_settings);
    this.wizardManifest = null;
    this.wizardEditableFields = [];
    this.error = '';
    this.message = '';
    this.loadWizardManifest();
    this.loadWizardEditableFields();
  }

  /** Coerce API agent_settings JSON into form-friendly scalar values. */
  private normalizeWizardSettings(
    raw: Record<string, unknown> | undefined
  ): Record<string, string | number | boolean> {
    const out: Record<string, string | number | boolean> = {};
    if (!raw) return out;
    for (const [key, value] of Object.entries(raw)) {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        out[key] = value;
      }
    }
    return out;
  }

  private applyDefaultWizardAgentId(): void {
    if (!this.showAgentWizard || this.wizardAgentId) return;
    if (this.agentsCatalog.length === 1) {
      this.wizardAgentId = this.agentsCatalog[0].agent_id;
      this.loadWizardManifest();
      this.loadWizardEditableFields();
    }
  }

  canInstallAgent(): boolean {
    const nameOk = !!this.wizardName.trim();
    const typeOk =
      !!this.wizardAgentId &&
      this.agentsCatalog.some((a) => a.agent_id === this.wizardAgentId);
    if (!this.wizardManifest) return nameOk && typeOk;
    const bindingsOk = this.wizardManifest.required_roles.every(
      (role) => !!this.wizardBindings[role]
    );
    return nameOk && typeOk && bindingsOk && !!this.environmentId;
  }

  cancelAgentWizard(): void {
    this.showAgentWizard = false;
    this.editingAgentId = null;
  }

  onWizardAgentChange(): void {
    this.wizardBindings = {};
    this.wizardSettings = {};
    this.loadWizardManifest();
    this.loadWizardEditableFields();
  }

  loadWizardManifest(): void {
    if (!this.wizardAgentId) {
      this.wizardManifest = null;
      return;
    }
    this.api.getAgentConnectionManifest(this.wizardAgentId).subscribe({
      next: (m) => {
        this.wizardManifest = m;
      },
      error: () => {
        this.wizardManifest = null;
      },
    });
  }

  loadWizardEditableFields(): void {
    if (!this.wizardAgentId) {
      this.wizardEditableFields = [];
      return;
    }
    this.api.getEditableSettings(this.wizardAgentId).subscribe({
      next: (res) => {
        this.wizardEditableFields = res.fields || [];
        this.applyWizardSettingDefaults();
      },
    });
  }

  private static readonly SETTING_GROUP_LABELS: Record<string, string> = {
    recommendation: 'Recommendation behavior',
    llm_sampling: 'Language model sampling',
    rag_retrieval: 'Knowledge search retrieval',
  };

  wizardSettingGroups(): string[] {
    const order = ['recommendation', 'llm_sampling', 'rag_retrieval'];
    const present = new Set(
      this.wizardEditableFields.map((f) => f.group || 'recommendation')
    );
    return order.filter((g) => present.has(g));
  }

  fieldsForWizardGroup(group: string): EditableSettingsField[] {
    return this.wizardEditableFields.filter(
      (f) => (f.group || 'recommendation') === group
    );
  }

  wizardGroupLabel(group: string): string {
    return WorkspaceDetailComponent.SETTING_GROUP_LABELS[group] || group;
  }

  private applyWizardSettingDefaults(): void {
    for (const f of this.wizardEditableFields) {
      if (this.wizardSettings[f.key] !== undefined) continue;
      if (f.key === 'recommendation_cost_retry_enabled') {
        this.wizardSettings[f.key] = true;
      } else if (f.key === 'recommendation_auto_termination_minutes') {
        this.wizardSettings[f.key] = 0;
      } else if (f.key === 'llm_temperature') {
        this.wizardSettings[f.key] = 0;
      } else if (f.key === 'llm_top_p') {
        this.wizardSettings[f.key] = 1;
      } else if (f.key === 'rag_top_k_recommendations') {
        this.wizardSettings[f.key] = 3;
      } else if (f.key === 'rag_top_k_jobs') {
        this.wizardSettings[f.key] = 5;
      }
    }
  }

  wizardRoles(): string[] {
    if (!this.wizardManifest) return [];
    return [
      ...this.wizardManifest.required_roles,
      ...this.wizardManifest.optional_roles,
    ];
  }

  isRoleRequired(role: string): boolean {
    return this.wizardManifest?.required_roles.includes(role) ?? false;
  }

  allowedTypesForRole(role: string): string[] {
    const spec = this.wizardManifest?.roles[role];
    if (Array.isArray(spec)) return spec;
    if (spec?.kind === 'connection') return spec.connection_types || [];
    return [];
  }

  connectionTypeLabel(type: string): string {
    return this.connectionTypeMeta(type)?.label || type;
  }

  agentCatalogName(agentId: string): string {
    return this.agentsCatalog.find((a) => a.agent_id === agentId)?.name || agentId;
  }

  roleLabel(role: string): string {
    return this.wizardManifest?.role_ui?.[role]?.label || role;
  }

  roleHelp(role: string): string {
    return this.wizardManifest?.role_ui?.[role]?.help || '';
  }

  allowedTypesLabel(role: string): string {
    return this.allowedTypesForRole(role)
      .map((t) => this.connectionTypeLabel(t))
      .join(' or ');
  }

  buildWizardSettings(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of this.wizardEditableFields) {
      const v = this.wizardSettings[f.key];
      if (v === undefined || v === '' || v === null) continue;
      if (f.type === 'number') out[f.key] = Number(v);
      else if (f.type === 'boolean') out[f.key] = v === true || v === 'true';
      else out[f.key] = v;
    }
    return out;
  }

  saveWorkspaceAgent(): void {
    if (!this.environmentId) {
      this.error = 'Select an environment in the header first.';
      return;
    }
    if (!this.wizardName.trim()) {
      this.error = 'Agent name is required.';
      return;
    }
    if (!this.wizardAgentId || !this.agentsCatalog.some((a) => a.agent_id === this.wizardAgentId)) {
      this.error = 'Agent type is required.';
      return;
    }
    if (!this.wizardManifest) {
      this.error = 'Agent manifest not loaded.';
      return;
    }
    for (const role of this.wizardManifest.required_roles) {
      if (!this.wizardBindings[role]) {
        this.error = this.isDatasetRole(role)
          ? `Select a dataset for ${this.roleLabel(role)}.`
          : `Select a connection for ${this.roleLabel(role)}.`;
        return;
      }
    }
    this.saving = true;
    this.error = '';
    const bindings: Record<string, string> = {};
    for (const role of this.wizardRoles()) {
      const id = this.wizardBindings[role];
      if (id) bindings[role] = id;
    }
    const payload = {
      environment_id: this.environmentId,
      name: this.wizardName.trim(),
      bindings,
      agent_settings: this.buildWizardSettings(),
      workspace_name: this.workspaceName || this.workspaceId(),
    };

    const req = this.editingAgentId
      ? this.api.updateWorkspaceAgent(this.workspaceId(), this.editingAgentId, payload)
      : this.api.createWorkspaceAgent(this.workspaceId(), {
          ...payload,
          agent_id: this.wizardAgentId,
        });

    req.subscribe({
      next: () => {
        this.saving = false;
        this.message = this.editingAgentId
          ? 'Agent configuration updated.'
          : 'Agent installed on workspace.';
        this.cancelAgentWizard();
        this.refresh();
      },
      error: (err) => {
        this.saving = false;
        this.error = parseApiError(
          err,
          this.editingAgentId ? 'Update agent failed' : 'Install agent failed'
        );
      },
    });
  }

  deleteWorkspaceAgent(wa: WorkspaceAgent): void {
    if (!confirm(`Remove "${wa.name}" from this workspace?`)) return;
    this.api.deleteWorkspaceAgent(this.workspaceId(), wa.id).subscribe({
      next: () => {
        this.message = 'Workspace agent removed.';
        this.refresh();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Delete failed');
      },
    });
  }

  bindingSummary(wa: WorkspaceAgent): string {
    const roleLabels: Record<string, string> = {
      metrics: 'Job metrics',
      llm: 'Language model',
      rag: 'Knowledge search',
    };
    const parts: string[] = [];
    for (const [role, id] of Object.entries(wa.bindings || {})) {
      const ds = this.envDatasets.find((d) => d.id === id);
      if (ds) {
        parts.push(`${roleLabels[role] || role}: ${ds.name}`);
        continue;
      }
      const conn = this.envConnections.find((c) => c.id === id);
      parts.push(`${roleLabels[role] || role}: ${conn?.name || id}`);
    }
    if (!wa.bindings?.['rag'] && wa.agent_id === 'dbx_cluster_tuning_agent') {
      parts.push('Knowledge search: not set');
    }
    return parts.length ? parts.join(' · ') : '—';
  }

  canAddAgent(): boolean {
    return !!this.environmentId && (this.envConnections.length > 0 || this.envDatasets.length > 0);
  }

  openJobs(): void {
    this.workspaceSelection.setLastWorkspaceId(this.workspaceId());
    void this.router.navigate(['/app/jobs'], {
      queryParams: { workspaceId: this.workspaceId() },
    });
  }
}
