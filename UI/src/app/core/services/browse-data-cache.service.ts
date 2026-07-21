import { Injectable } from '@angular/core';
import { Observable, of, tap } from 'rxjs';

/**
 * In-memory cache for Databricks browse API responses (workspaces, jobs, metrics).
 * Survives route navigation; cleared on env/connection/dataset change or explicit refresh/apply.
 */
@Injectable({ providedIn: 'root' })
export class BrowseDataCacheService {
  private store = new Map<string, unknown>();

  private datasetToken(datasetId: string | null | undefined): string {
    return datasetId?.trim() || '_';
  }

  workspacesKey(
    environmentId: string,
    connectionId: string | null | undefined,
    datasetId?: string | null
  ): string {
    return `workspaces:${environmentId}:${connectionId?.trim() || '_'}:${this.datasetToken(datasetId)}`;
  }

  jobsKey(
    environmentId: string | null | undefined,
    connectionId: string | null | undefined,
    datasetId: string | null | undefined,
    workspaceId: string,
    startDate: string,
    endDate: string
  ): string {
    return `jobs:v2:${environmentId || '_'}:${connectionId?.trim() || '_'}:${this.datasetToken(datasetId)}:${workspaceId}:${startDate}:${endDate}`;
  }

  jobMetricsKey(
    environmentId: string | null | undefined,
    connectionId: string | null | undefined,
    datasetId: string | null | undefined,
    workspaceId: string,
    jobId: string,
    startDate: string,
    endDate: string
  ): string {
    return `metrics:${environmentId || '_'}:${connectionId?.trim() || '_'}:${this.datasetToken(datasetId)}:${workspaceId}:${jobId}:${startDate}:${endDate}`;
  }

  jobRunsKey(
    environmentId: string | null | undefined,
    connectionId: string | null | undefined,
    datasetId: string | null | undefined,
    workspaceId: string,
    jobId: string,
    startDate: string,
    endDate: string
  ): string {
    return `runs:v2:${environmentId || '_'}:${connectionId?.trim() || '_'}:${this.datasetToken(datasetId)}:${workspaceId}:${jobId}:${startDate}:${endDate}`;
  }

  recommendationsKey(workspaceId: string, jobId: string, limit: number): string {
    return `recs:${workspaceId}:${jobId}:${limit}`;
  }

  peek<T>(key: string): T | undefined {
    return this.store.get(key) as T | undefined;
  }

  get<T>(key: string, fetch: () => Observable<T>, force = false): Observable<T> {
    if (!force && this.store.has(key)) {
      return of(this.store.get(key) as T);
    }
    return fetch().pipe(tap((data) => this.store.set(key, data)));
  }

  delete(key: string): void {
    this.store.delete(key);
  }

  /** Drop cached browse rows for one environment (all connections/datasets). */
  invalidateEnvironment(environmentId: string): void {
    const token = `:${environmentId}:`;
    for (const key of [...this.store.keys()]) {
      if (key.includes(token)) {
        this.store.delete(key);
      }
    }
  }

  clear(): void {
    this.store.clear();
  }
}
