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

export interface JobSummary {
  workspace_id: string;
  job_id: string;
  job_name?: string;
  workload_type?: string;
  avg_cpu_utilization_pct?: number;
  avg_memory_utilization_pct?: number;
  total_runs?: number;
  avg_duration_seconds?: number;
  current_node_type?: string;
  current_min_workers?: number;
  current_max_workers?: number;
  last_run_date?: string;
}

export interface JobRunSummary {
  job_run_id: string;
  run_date?: string;
  job_duration_seconds?: number;
  avg_cpu_utilization_pct?: number;
  avg_memory_utilization_pct?: number;
  avg_nodes_consumed?: number;
  peak_cpu_utilization_pct?: number;
  peak_memory_utilization_pct?: number;
  total_cost_usd?: number;
  current_node_type?: string;
  current_min_workers?: number;
  current_max_workers?: number;
  workload_type?: string;
  task_count?: number;
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
  job_run_id: string;
  start_date?: string;
  end_date?: string;
  include_explanation?: boolean;
}

export interface GenerateRecommendationResponse {
  request_id?: string;
  job_run_id?: string;
  current_configuration?: Record<string, unknown>;
  recommendation: Record<string, unknown>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  reason_codes?: string[];
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

  getWorkspaces(): Observable<Workspace[]> {
    return this.http.get<Workspace[]>(`${API_BASE}/workspaces`).pipe(
      catchError((err) => {
        console.error('getWorkspaces error', err);
        return of([]);
      })
    );
  }

  getJobs(workspaceId: string, start_date?: string, end_date?: string): Observable<JobSummary[]> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    return this.http
      .get<JobSummary[]>(`${API_BASE}/workspaces/${workspaceId}/jobs`, { params })
      .pipe(
        catchError((err) => {
          console.error('getJobs error', err);
          return of([]);
        })
      );
  }

  getJobRuns(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string
  ): Observable<JobRunSummary[]> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    return this.http
      .get<JobRunSummary[]>(
        `${API_BASE}/workspaces/${workspaceId}/jobs/${jobId}/runs`,
        { params }
      )
      .pipe(
        catchError((err) => {
          console.error('getJobRuns error', err);
          return of([]);
        })
      );
  }

  getJobMetrics(
    workspaceId: string,
    jobId: string,
    start_date?: string,
    end_date?: string
  ): Observable<JobMetricsResponse | null> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    return this.http
      .get<JobMetricsResponse>(
        `${API_BASE}/workspaces/${workspaceId}/jobs/${jobId}/metrics`,
        { params }
      )
      .pipe(catchError(() => of(null)));
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
              get_started_route: '/app/workspaces',
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
