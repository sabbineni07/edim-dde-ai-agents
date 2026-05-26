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
  recommendation: Record<string, unknown>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  token_usage_analysis?: Record<string, unknown>;
  request_log?: Record<string, unknown>;
  cost_usage_summary?: Record<string, unknown>;
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

export interface AgentProfile {
  id: string;
  agent_id: string;
  name: string;
  overrides: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface GenerateRecommendationRequest {
  agent_id?: string;
  profile_id?: string | null;
  job_id: string;
  job_run_id: string;
  start_date: string;
  end_date: string;
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

  getWorkspaces(start_date?: string, end_date?: string): Observable<Workspace[]> {
    let params = new HttpParams();
    if (start_date) params = params.set('start_date', start_date);
    if (end_date) params = params.set('end_date', end_date);
    return this.http.get<Workspace[]>(`${API_BASE}/workspaces`, { params }).pipe(
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
      .pipe(
        catchError((err) => {
          console.error('getJobMetrics error', err);
          return of(null);
        })
      );
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

  getAgents(): Observable<{ agent_ids: string[] }> {
    return this.http.get<{ agent_ids: string[] }>(`${API_BASE}/agents/`).pipe(
      catchError((err) => {
        console.error('getAgents error', err);
        return of({ agent_ids: ['job_run_cluster_sizing'] });
      })
    );
  }

  getAgentProfiles(agentId?: string): Observable<AgentProfile[]> {
    let params = new HttpParams();
    if (agentId) params = params.set('agent_id', agentId);
    return this.http.get<AgentProfile[]>(`${API_BASE}/agent-profiles/`, { params }).pipe(
      catchError((err) => {
        console.error('getAgentProfiles error', err);
        return of([]);
      })
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
