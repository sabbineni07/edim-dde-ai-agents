import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, of } from 'rxjs';

const API_BASE = '/api';

export interface Workspace {
  workspace_id: string;
  workspace_name: string;
  job_count: number;
  first_seen_date?: string;
  last_seen_date?: string;
}

export interface LocalDatasetInfo {
  source: 'upload' | 'sample';
  filename: string;
  uploaded_at?: string | null;
  row_count?: number | null;
  file_size_bytes?: number | null;
  using_sample: boolean;
}

export interface PlatformEnvironment {
  id: string;
  code: string;
  display_name: string;
  description: string;
  environment_tier: string;
  source_type: 'databricks_uc' | 'local_csv';
  catalog_name?: string | null;
  schema_name?: string | null;
  table_name?: string | null;
  table_fqn?: string | null;
  databricks_server_hostname?: string | null;
  databricks_http_path?: string | null;
  default_metrics_connection_id?: string | null;
  default_llm_connection_id?: string | null;
  metrics_connection_count?: number;
  sort_order: number;
  icon: string;
  is_enabled?: boolean;
  readiness: 'ready' | 'needs_connection' | 'needs_upload' | 'unknown';
  local_dataset?: LocalDatasetInfo | null;
}

export interface PlatformEnvironmentUpdate {
  display_name?: string;
  description?: string;
  environment_tier?: string;
  sort_order?: number;
  icon?: string;
  is_enabled?: boolean;
}

export interface EnvironmentConnection {
  id: string;
  environment_id: string;
  name: string;
  connection_type: string;
  purpose: 'metrics' | 'llm' | 'rag';
  config: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  workspace_id: string;
  job_id: string;
  job_name?: string;
  job_type?: string;
  avg_worker_cpu_utilization_pct?: number;
  avg_worker_memory_utilization_pct?: number;
  total_runs?: number;
  avg_job_run_duration_seconds?: number;
  azure_worker_vm_size?: string;
  max_worker_nodes_provisioned?: number;
  last_job_run_date?: string;
}

export interface JobRunSummary {
  cluster_id: string;
  job_run_date?: string;
  job_run_duration_seconds?: number;
  avg_worker_cpu_utilization_pct?: number;
  avg_worker_memory_utilization_pct?: number;
  avg_worker_nodes_consumed?: number;
  total_worker_vcpus_provisioned?: number;
  total_worker_gb_provisioned?: number;
  peak_worker_cpu_utilization_pct?: number;
  peak_worker_memory_utilization_pct?: number;
  azure_worker_vm_size?: string;
  max_worker_nodes_provisioned?: number;
  job_type?: string;
}

export interface JobMetricsResponse {
  workspace_id: string;
  job_id: string;
  start_date: string;
  end_date: string;
  metrics: Record<string, unknown>;
}

export interface LifecycleEventSummary {
  id?: number;
  from_status?: string | null;
  to_status: string;
  changed_by: string;
  changed_at?: string;
  notes?: string | null;
}

export interface RecommendationHistoryEntry {
  request_id: string;
  job_id: string;
  job_run_id?: string;
  workspace_id?: string;
  timestamp: string;
  lifecycle_status?: string;
  lifecycle_status_label?: string;
  lifecycle_updated_at?: string;
  lifecycle_updated_by?: string;
  allowed_next_statuses?: string[];
  lifecycle_events?: LifecycleEventSummary[];
  api_request_status?: string;
  comparison?: Record<string, unknown>;
  reason_codes?: string[];
  recommendation: Record<string, unknown>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  token_usage_analysis?: Record<string, unknown>;
  request_log?: Record<string, unknown>;
  cost_usage_summary?: Record<string, unknown>;
}

export interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  get_started_route: string;
}

export interface EditableSettingsField {
  key: string;
  label: string;
  type: string;
  options?: string[];
  placeholder?: string;
  help?: string;
  min?: number;
  max?: number;
  step?: number;
}

export interface UiHints {
  guardrail_max_date_range_days: number;
  use_local_data: boolean;
  sample_data_start_date: string;
  sample_data_end_date: string;
  default_agent_id: string;
  admin_usernames?: string[];
}

export interface ConnectionTypeField {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  placeholder?: string;
  help?: string;
  options?: string[];
}

export interface ConnectionTypeMeta {
  connection_type: string;
  label: string;
  description: string;
  fields: ConnectionTypeField[];
  auth_note?: string;
}

export interface AgentRoleUi {
  label: string;
  help: string;
}

export interface WorkspaceConnection {
  id: string;
  workspace_id: string;
  workspace_name?: string | null;
  connection_type: string;
  name: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceAgent {
  id: string;
  workspace_id: string;
  workspace_name?: string | null;
  agent_id: string;
  name: string;
  bindings: Record<string, string>;
  agent_settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentConnectionManifest {
  agent_id: string;
  roles: Record<string, string[]>;
  role_ui?: Record<string, AgentRoleUi>;
  required_roles: string[];
  optional_roles: string[];
  agent_settings_keys: string[];
  auth_note?: string;
}

export interface GenerateRecommendationRequest {
  agent_id?: string;
  workspace_agent_id?: string | null;
  job_id: string;
  cluster_id: string;
  job_run_id?: string;
  start_date?: string;
  end_date?: string;
  include_explanation?: boolean;
}

export interface GenerateRecommendationResponse {
  request_id?: string;
  cluster_id?: string;
  job_run_id?: string;
  current_configuration?: Record<string, unknown>;
  recommendation: Record<string, unknown>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  reason_codes?: string[];
  job_cluster_metrics?: Record<string, unknown>;
  job_run_ingest?: Record<string, unknown>;
  sizing_hints?: Record<string, unknown>;
  llm_recommendation?: Record<string, unknown>;
  guardrail_recommendation?: Record<string, unknown>;
  guardrail_adjustments?: Array<Record<string, unknown>>;
  recommendation_attempts?: number;
  comparison?: Record<string, unknown>;
  token_usage_analysis?: Record<string, unknown>;
}

export interface LifecycleMeta {
  statuses: string[];
  display_labels: Record<string, string>;
  allowed_transitions: Record<string, string[]>;
}

export interface LifecycleTransitionRequest {
  status: string;
  changed_by?: string;
  notes?: string;
}

export interface ChatRequest {
  question: string;
  workspace_id?: string;
  job_id?: string;
  start_date?: string;
  end_date?: string;
}

export interface ChatResponse {
  answer: string;
  context_summary: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}

  getUiHints(): Observable<UiHints> {
    return this.http.get<UiHints>(`${API_BASE}/platform/ui-hints`).pipe(
      catchError(() =>
        of({
          guardrail_max_date_range_days: 30,
          use_local_data: true,
          sample_data_start_date: '2026-06-01',
          sample_data_end_date: '2026-06-03',
          default_agent_id: 'dbx_cluster_tuning_agent',
        })
      )
    );
  }

  getEnvironments(): Observable<PlatformEnvironment[]> {
    return this.http.get<PlatformEnvironment[]>(`${API_BASE}/environments`).pipe(
      catchError((err) => {
        console.error('getEnvironments error', err);
        return of([]);
      })
    );
  }

  updateEnvironment(
    environmentId: string,
    body: PlatformEnvironmentUpdate
  ): Observable<PlatformEnvironment> {
    return this.http.put<PlatformEnvironment>(`${API_BASE}/environments/${environmentId}`, body);
  }

  getLocalDataset(): Observable<LocalDatasetInfo> {
    return this.http.get<LocalDatasetInfo>(`${API_BASE}/environments/local/dataset`);
  }

  uploadLocalCsv(file: File): Observable<LocalDatasetInfo> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<LocalDatasetInfo>(`${API_BASE}/environments/local/upload`, form);
  }

  resetLocalDataset(): Observable<LocalDatasetInfo> {
    return this.http.delete<LocalDatasetInfo>(`${API_BASE}/environments/local/dataset`);
  }

  downloadLocalTemplate(): void {
    window.open(`${API_BASE}/environments/local/template`, '_blank');
  }

  private withEnvironmentParams(
    params: HttpParams,
    environmentId?: string | null,
    connectionId?: string | null
  ): HttpParams {
    const envId = (environmentId ?? '').trim();
    let out = envId ? params.set('environment_id', envId) : params;
    const connId = (connectionId ?? '').trim();
    if (connId) out = out.set('connection_id', connId);
    return out;
  }

  getEnvironmentConnections(
    environmentId: string,
    purpose?: string
  ): Observable<EnvironmentConnection[]> {
    let params = new HttpParams();
    if (purpose) params = params.set('purpose', purpose);
    return this.http.get<EnvironmentConnection[]>(
      `${API_BASE}/environments/${environmentId}/connections`,
      { params }
    );
  }

  createEnvironmentConnection(
    environmentId: string,
    body: {
      name: string;
      connection_type: string;
      purpose?: string;
      config: Record<string, unknown>;
      set_default?: boolean;
    }
  ): Observable<EnvironmentConnection> {
    return this.http.post<EnvironmentConnection>(
      `${API_BASE}/environments/${environmentId}/connections`,
      body
    );
  }

  updateEnvironmentConnection(
    environmentId: string,
    connectionId: string,
    body: { name?: string; config?: Record<string, unknown> }
  ): Observable<EnvironmentConnection> {
    return this.http.put<EnvironmentConnection>(
      `${API_BASE}/environments/${environmentId}/connections/${connectionId}`,
      body
    );
  }

  deleteEnvironmentConnection(
    environmentId: string,
    connectionId: string
  ): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${API_BASE}/environments/${environmentId}/connections/${connectionId}`
    );
  }

  setDefaultEnvironmentConnection(
    environmentId: string,
    connectionId: string,
    purpose?: string
  ): Observable<EnvironmentConnection> {
    let params = new HttpParams();
    if (purpose) params = params.set('purpose', purpose);
    return this.http.post<EnvironmentConnection>(
      `${API_BASE}/environments/${environmentId}/connections/${connectionId}/set-default`,
      {},
      { params }
    );
  }

  getEnvironmentConnectionsByType(
    environmentId: string,
    connectionType: string
  ): Observable<EnvironmentConnection[]> {
    let params = new HttpParams().set('connection_type', connectionType);
    return this.http.get<EnvironmentConnection[]>(
      `${API_BASE}/environments/${environmentId}/connections`,
      { params }
    );
  }

  /** Browse workspaces; errors propagate (use in Workspaces UI). */
  browseWorkspaces(
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<Workspace[]> {
    let params = new HttpParams();
    params = this.withEnvironmentParams(params, environmentId, connectionId);
    return this.http.get<Workspace[]>(`${API_BASE}/workspaces`, { params });
  }

  /** @deprecated Prefer browseWorkspaces when errors should surface in the UI. */
  getWorkspaces(
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<Workspace[]> {
    return this.browseWorkspaces(environmentId, connectionId).pipe(
      catchError((err) => {
        console.error('getWorkspaces error', err);
        return of([]);
      })
    );
  }

  getJobs(
    workspaceId: string,
    start_date?: string,
    end_date?: string,
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<JobSummary[]> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    params = this.withEnvironmentParams(params, environmentId, connectionId);
    return this.http
      .get<JobSummary[]>(`${API_BASE}/workspaces/${workspaceId}/jobs`, { params })
      .pipe(
        catchError((err) => {
          console.error('getJobs error', err);
          return of([]);
        })
      );
  }

  /** Browse job runs; errors propagate (use in Job detail UI). */
  browseJobRuns(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string,
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<JobRunSummary[]> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    params = this.withEnvironmentParams(params, environmentId, connectionId);
    return this.http.get<JobRunSummary[]>(
      `${API_BASE}/workspaces/${workspaceId}/jobs/${jobId}/runs`,
      { params }
    );
  }

  /** @deprecated Prefer browseJobRuns when errors should surface in the UI. */
  getJobRuns(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string,
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<JobRunSummary[]> {
    return this.browseJobRuns(
      workspaceId,
      jobId,
      start_date,
      end_date,
      environmentId,
      connectionId
    ).pipe(
      catchError((err) => {
        console.error('getJobRuns error', err);
        return of([]);
      })
    );
  }

  /** Browse job metrics; errors propagate (use in Job detail UI). */
  browseJobMetrics(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string,
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<JobMetricsResponse> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    params = this.withEnvironmentParams(params, environmentId, connectionId);
    return this.http.get<JobMetricsResponse>(
      `${API_BASE}/workspaces/${workspaceId}/jobs/${jobId}/metrics`,
      { params }
    );
  }

  /** @deprecated Prefer browseJobMetrics when errors should surface in the UI. */
  getJobMetrics(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string,
    environmentId?: string | null,
    connectionId?: string | null
  ): Observable<JobMetricsResponse | null> {
    return this.browseJobMetrics(
      workspaceId,
      jobId,
      start_date,
      end_date,
      environmentId,
      connectionId
    ).pipe(catchError(() => of(null)));
  }

  getRecommendations(
    workspaceId: string,
    jobId: string,
    limit = 5
  ): Observable<RecommendationHistoryEntry[]> {
    return this.http
      .get<RecommendationHistoryEntry[]>(
        `${API_BASE}/workspaces/${workspaceId}/jobs/${jobId}/recommendations`,
        { params: { limit: limit.toString() } }
      )
      .pipe(
        catchError((err) => {
          console.error('getRecommendations error', err);
          return of([]);
        })
      );
  }

  getAgents(): Observable<{ agents: AgentInfo[] }> {
    return this.http.get<{ agents: AgentInfo[] }>(`${API_BASE}/agents/`).pipe(
      catchError((err) => {
        console.error('getAgents error', err);
        return of({
          agents: [
            {
              agent_id: 'dbx_cluster_tuning_agent',
              name: 'DBX Cluster Tuning Agent',
              description: 'Per-run cluster right-sizing.',
              get_started_route: '/app/environments',
            },
          ],
        });
      })
    );
  }

  getEditableSettings(agentId: string): Observable<{ agent_id: string; fields: EditableSettingsField[] }> {
    return this.http.get<{ agent_id: string; fields: EditableSettingsField[] }>(
      `${API_BASE}/agents/${agentId}/editable-settings`
    );
  }

  previewEffectiveSettings(
    agentId: string,
    overrides: Record<string, unknown>
  ): Observable<{ agent_id: string; effective_settings: Record<string, unknown> }> {
    return this.http.post<{ agent_id: string; effective_settings: Record<string, unknown> }>(
      `${API_BASE}/agents/${agentId}/effective-settings-preview`,
      { overrides }
    );
  }

  getConnectionTypes(): Observable<{ connection_types: ConnectionTypeMeta[] }> {
    return this.http
      .get<{ connection_types: ConnectionTypeMeta[] }>(`${API_BASE}/platform/connection-types`)
      .pipe(
        catchError((err) => {
          console.error('getConnectionTypes error', err);
          return of({ connection_types: [] });
        })
      );
  }

  getWorkspaceConnections(
    workspaceId: string,
    connectionType?: string
  ): Observable<WorkspaceConnection[]> {
    let params = new HttpParams();
    if (connectionType) params = params.set('connection_type', connectionType);
    return this.http
      .get<WorkspaceConnection[]>(`${API_BASE}/workspaces/${workspaceId}/connections`, { params })
      .pipe(
        catchError((err) => {
          console.error('getWorkspaceConnections error', err);
          return of([]);
        })
      );
  }

  createWorkspaceConnection(
    workspaceId: string,
    body: {
      connection_type: string;
      name: string;
      config: Record<string, unknown>;
      workspace_name?: string;
    }
  ): Observable<WorkspaceConnection> {
    return this.http.post<WorkspaceConnection>(
      `${API_BASE}/workspaces/${workspaceId}/connections`,
      body
    );
  }

  updateWorkspaceConnection(
    workspaceId: string,
    connectionId: string,
    body: { name?: string; config?: Record<string, unknown>; workspace_name?: string }
  ): Observable<WorkspaceConnection> {
    return this.http.put<WorkspaceConnection>(
      `${API_BASE}/workspaces/${workspaceId}/connections/${connectionId}`,
      body
    );
  }

  deleteWorkspaceConnection(
    workspaceId: string,
    connectionId: string
  ): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${API_BASE}/workspaces/${workspaceId}/connections/${connectionId}`
    );
  }

  getWorkspaceAgents(workspaceId: string, agentId?: string): Observable<WorkspaceAgent[]> {
    let params = new HttpParams();
    if (agentId) params = params.set('agent_id', agentId);
    return this.http
      .get<WorkspaceAgent[]>(`${API_BASE}/workspaces/${workspaceId}/agents`, { params })
      .pipe(
        catchError((err) => {
          console.error('getWorkspaceAgents error', err);
          return of([]);
        })
      );
  }

  getAgentConnectionManifest(agentId: string): Observable<AgentConnectionManifest> {
    return this.http.get<AgentConnectionManifest>(
      `${API_BASE}/agents/${agentId}/connection-manifest`
    );
  }

  createWorkspaceAgent(
    workspaceId: string,
    body: {
      agent_id: string;
      name: string;
      bindings: Record<string, string>;
      agent_settings?: Record<string, unknown>;
      workspace_name?: string;
    }
  ): Observable<WorkspaceAgent> {
    return this.http.post<WorkspaceAgent>(`${API_BASE}/workspaces/${workspaceId}/agents`, body);
  }

  updateWorkspaceAgent(
    workspaceId: string,
    workspaceAgentId: string,
    body: {
      name?: string;
      bindings?: Record<string, string>;
      agent_settings?: Record<string, unknown>;
      workspace_name?: string;
    }
  ): Observable<WorkspaceAgent> {
    return this.http.put<WorkspaceAgent>(
      `${API_BASE}/workspaces/${workspaceId}/agents/${workspaceAgentId}`,
      body
    );
  }

  deleteWorkspaceAgent(
    workspaceId: string,
    workspaceAgentId: string
  ): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(
      `${API_BASE}/workspaces/${workspaceId}/agents/${workspaceAgentId}`
    );
  }

  generateRecommendation(
    body: GenerateRecommendationRequest
  ): Observable<GenerateRecommendationResponse> {
    return this.http.post<GenerateRecommendationResponse>(
      `${API_BASE}/recommendations/generate`,
      body
    );
  }

  getLifecycleMeta(): Observable<LifecycleMeta> {
    return this.http.get<LifecycleMeta>(`${API_BASE}/recommendations/lifecycle/meta`);
  }

  updateRecommendationLifecycle(
    requestId: string,
    body: LifecycleTransitionRequest
  ): Observable<Record<string, unknown>> {
    return this.http.patch<Record<string, unknown>>(
      `${API_BASE}/recommendations/${requestId}/lifecycle`,
      body
    );
  }

  chat(req: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${API_BASE}/chat`, req);
  }
}
