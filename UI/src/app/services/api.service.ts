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

export interface JobMetricsResponse {
  workspace_id: string;
  job_id: string;
  start_date: string;
  end_date: string;
  metrics: Record<string, unknown>;
}

export interface RecommendationHistoryEntry {
  request_id: string;
  job_id: string;
  workspace_id?: string;
  timestamp: string;
  recommendation: Record<string, unknown>;
  explanation?: string;
  pattern_analysis?: string;
  risk_assessment?: Record<string, unknown>;
  token_usage_analysis?: Record<string, unknown>;
  request_log?: Record<string, unknown>;
  cost_usage_summary?: Record<string, unknown>;
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

  generateRecommendation(body: {
    job_id: string;
    start_date: string;
    end_date: string;
  }): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(
      `${API_BASE}/recommendations/generate`,
      body
    );
  }

  chat(req: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${API_BASE}/chat`, req);
  }
}
