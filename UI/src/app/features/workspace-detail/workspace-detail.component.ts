import { Component, OnInit, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  AgentConnectionManifest,
  AgentInfo,
  ApiService,
  ConnectionTypeMeta,
  EditableSettingsField,
  WorkspaceAgent,
  WorkspaceConnection,
} from '../../services/api.service';
import { parseApiError } from '../../core/api-error.util';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';

@Component({
  selector: 'app-workspace-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './workspace-detail.component.html',
  styleUrls: ['./workspace-detail.component.css'],
})
export class WorkspaceDetailComponent implements OnInit {
  workspaceId = input.required<string>();

  activeTab: 'connections' | 'agents' = 'connections';
  workspaceName = '';

  connectionTypes: ConnectionTypeMeta[] = [];
  connections: WorkspaceConnection[] = [];
  workspaceAgents: WorkspaceAgent[] = [];
  agentsCatalog: AgentInfo[] = [];

  loadingConnections = true;
  loadingAgents = true;
  saving = false;
  message = '';
  error = '';

  showConnectionForm = false;
  editingConnectionId: string | null = null;
  connType = 'local_dataset';
  connName = '';
  connConfig: Record<string, string> = {};

  showAgentWizard = false;
  wizardAgentId = 'dbx_cluster_tuning_agent';
  wizardName = '';
  wizardBindings: Record<string, string> = {};
  wizardManifest: AgentConnectionManifest | null = null;
  wizardSettings: Record<string, string | number | boolean> = {};
  wizardEditableFields: EditableSettingsField[] = [];

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    private workspaceSelection: WorkspaceSelectionService
  ) {}

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((qp) => {
      const tab = qp.get('tab');
      if (tab === 'agents' || tab === 'connections') {
        this.activeTab = tab;
      }
    });
    this.api.getConnectionTypes().subscribe({
      next: (res) => {
        this.connectionTypes = res.connection_types || [];
        if (this.connectionTypes.length && !this.connectionTypes.some((t) => t.connection_type === this.connType)) {
          this.connType = this.connectionTypes[0].connection_type;
        }
      },
    });
    this.api.getAgents().subscribe({
      next: (res) => {
        this.agentsCatalog = res.agents || [];
      },
    });
    this.refresh();
  }

  setTab(tab: 'connections' | 'agents'): void {
    this.activeTab = tab;
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  refresh(): void {
    const ws = this.workspaceId();
    this.loadingConnections = true;
    this.loadingAgents = true;
    this.error = '';
    this.api.getWorkspaceConnections(ws).subscribe({
      next: (list) => {
        this.connections = list;
        if (list.length && list[0].workspace_name) {
          this.workspaceName = list[0].workspace_name!;
        }
        this.loadingConnections = false;
      },
      error: () => {
        this.loadingConnections = false;
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

  connectionsForTypes(allowed: string[]): WorkspaceConnection[] {
    const set = new Set(allowed);
    return this.connections.filter((c) => set.has(c.connection_type));
  }

  startCreateConnection(): void {
    this.showConnectionForm = true;
    this.editingConnectionId = null;
    this.connName = '';
    this.connConfig = {};
    this.connType = this.connectionTypes[0]?.connection_type || 'local_dataset';
    this.message = '';
    this.error = '';
  }

  startEditConnection(c: WorkspaceConnection): void {
    this.showConnectionForm = true;
    this.editingConnectionId = c.id;
    this.connType = c.connection_type;
    this.connName = c.name;
    this.connConfig = {};
    const meta = this.connectionTypeMeta(c.connection_type);
    for (const f of meta?.fields || []) {
      const v = c.config[f.key];
      if (v != null) this.connConfig[f.key] = String(v);
    }
    this.message = '';
    this.error = '';
  }

  cancelConnectionForm(): void {
    this.showConnectionForm = false;
    this.editingConnectionId = null;
  }

  onConnectionTypeChange(): void {
    if (!this.editingConnectionId) {
      this.connConfig = {};
    }
  }

  buildConnectionConfig(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    const meta = this.connectionTypeMeta(this.connType);
    for (const f of meta?.fields || []) {
      const v = this.connConfig[f.key]?.trim();
      if (v) out[f.key] = v;
    }
    return out;
  }

  saveConnection(): void {
    if (!this.connName.trim()) {
      this.error = 'Connection name is required.';
      return;
    }
    this.saving = true;
    this.error = '';
    const ws = this.workspaceId();
    const config = this.buildConnectionConfig();
    const body = {
      connection_type: this.connType,
      name: this.connName.trim(),
      config,
      workspace_name: this.workspaceName || ws,
    };
    const obs = this.editingConnectionId
      ? this.api.updateWorkspaceConnection(ws, this.editingConnectionId, {
          name: body.name,
          config: body.config,
          workspace_name: body.workspace_name,
        })
      : this.api.createWorkspaceConnection(ws, body);
    obs.subscribe({
      next: () => {
        this.saving = false;
        this.message = this.editingConnectionId ? 'Connection updated.' : 'Connection created.';
        this.cancelConnectionForm();
        this.refresh();
      },
      error: (err) => {
        this.saving = false;
        this.error = parseApiError(err, 'Save connection failed');
      },
    });
  }

  deleteConnection(c: WorkspaceConnection): void {
    if (!confirm(`Delete connection "${c.name}"?`)) return;
    this.api.deleteWorkspaceConnection(this.workspaceId(), c.id).subscribe({
      next: () => {
        this.message = 'Connection deleted.';
        this.refresh();
      },
      error: (err) => {
        this.error = parseApiError(err, 'Delete failed');
      },
    });
  }

  startAddAgent(): void {
    this.showAgentWizard = true;
    this.wizardAgentId = 'dbx_cluster_tuning_agent';
    this.wizardName = '';
    this.wizardBindings = {};
    this.wizardSettings = {};
    this.error = '';
    this.message = '';
    this.loadWizardManifest();
    this.loadWizardEditableFields();
  }

  cancelAgentWizard(): void {
    this.showAgentWizard = false;
  }

  onWizardAgentChange(): void {
    this.wizardBindings = {};
    this.loadWizardManifest();
    this.loadWizardEditableFields();
  }

  loadWizardManifest(): void {
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
    this.api.getEditableSettings(this.wizardAgentId).subscribe({
      next: (res) => {
        this.wizardEditableFields = res.fields || [];
      },
    });
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
    return this.wizardManifest?.roles[role] || [];
  }

  connectionTypeLabel(type: string): string {
    return this.connectionTypeMeta(type)?.label || type;
  }

  connectionSummary(c: WorkspaceConnection): string {
    const cfg = c.config || {};
    const type = c.connection_type;
    if (type === 'databricks') {
      const host = cfg['databricks_server_hostname'];
      const table = cfg['databricks_job_cluster_metrics_table'];
      return [host, table].filter(Boolean).join(' · ') || '—';
    }
    if (type === 'local_dataset') {
      return String(cfg['local_data_path'] || '—');
    }
    if (type === 'ai_foundry') {
      return String(cfg['azure_openai_endpoint'] || '—');
    }
    if (type === 'ai_search') {
      const ep = cfg['azure_search_endpoint'];
      const idx = cfg['azure_search_index_name'];
      return [ep, idx].filter(Boolean).join(' / ') || '—';
    }
    if (type === 'faiss') {
      return String(cfg['faiss_index_path'] || '—');
    }
    return Object.entries(cfg)
      .map(([k, v]) => `${k}: ${v}`)
      .join('; ') || '—';
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
    if (!this.wizardName.trim()) {
      this.error = 'Agent name is required.';
      return;
    }
    if (!this.wizardManifest) {
      this.error = 'Agent manifest not loaded.';
      return;
    }
    for (const role of this.wizardManifest.required_roles) {
      if (!this.wizardBindings[role]) {
        this.error = `Select a connection for ${this.roleLabel(role)}.`;
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
    this.api
      .createWorkspaceAgent(this.workspaceId(), {
        agent_id: this.wizardAgentId,
        name: this.wizardName.trim(),
        bindings,
        agent_settings: this.buildWizardSettings(),
        workspace_name: this.workspaceName || this.workspaceId(),
      })
      .subscribe({
        next: () => {
          this.saving = false;
          this.message = 'Agent installed on workspace.';
          this.cancelAgentWizard();
          this.refresh();
        },
        error: (err) => {
          this.saving = false;
          this.error = parseApiError(err, 'Install agent failed');
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
    for (const [role, cid] of Object.entries(wa.bindings || {})) {
      const conn = this.connections.find((c) => c.id === cid);
      parts.push(`${roleLabels[role] || role}: ${conn?.name || cid}`);
    }
    return parts.length ? parts.join(' · ') : '—';
  }

  openJobs(): void {
    this.workspaceSelection.setLastWorkspaceId(this.workspaceId());
    void this.router.navigate(['/app/jobs'], {
      queryParams: { workspaceId: this.workspaceId() },
    });
  }
}
