import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, of, tap } from 'rxjs';
import { ApiService, EnvironmentConnection } from '../../services/api.service';

/** Browser-side cache for environment connections (refreshed explicitly or after CRUD). */
@Injectable({ providedIn: 'root' })
export class EnvironmentConnectionCacheService {
  private allByEnv = new Map<string, EnvironmentConnection[]>();
  private databricksByEnv = new Map<string, EnvironmentConnection[]>();
  private selectedConnection$ = new BehaviorSubject<EnvironmentConnection | null>(null);

  constructor(private api: ApiService) {}

  watchSelectedConnection(): Observable<EnvironmentConnection | null> {
    return this.selectedConnection$.asObservable();
  }

  getSelectedConnection(): EnvironmentConnection | null {
    return this.selectedConnection$.value;
  }

  setSelectedConnection(connection: EnvironmentConnection | null): void {
    this.selectedConnection$.next(connection);
  }

  /** All connections for an environment (Connections page). */
  getConnections(environmentId: string, force = false): Observable<EnvironmentConnection[]> {
    const eid = environmentId.trim();
    if (!eid) return of([]);
    if (!force && this.allByEnv.has(eid)) {
      return of(this.allByEnv.get(eid)!);
    }
    return this.api.getEnvironmentConnections(eid).pipe(
      tap((list) => this.storeAll(eid, list))
    );
  }

  /** Cached Databricks connections (no API call). */
  getCachedDatabricksConnections(environmentId: string): EnvironmentConnection[] | null {
    const eid = environmentId.trim();
    return eid && this.databricksByEnv.has(eid) ? this.databricksByEnv.get(eid)! : null;
  }

  /** Databricks connections for browse screens (Workspaces, Jobs, etc.). */
  getDatabricksConnections(environmentId: string, force = false): Observable<EnvironmentConnection[]> {
    const eid = environmentId.trim();
    if (!eid) return of([]);
    if (!force && this.databricksByEnv.has(eid)) {
      return of(this.databricksByEnv.get(eid)!);
    }
    return this.api.getEnvironmentConnectionsByType(eid, 'databricks').pipe(
      tap((list) => {
        this.databricksByEnv.set(eid, list);
        this.mergeDatabricksIntoAll(eid, list);
      })
    );
  }

  pickConnection(
    list: EnvironmentConnection[],
    preferredId: string | null
  ): EnvironmentConnection | null {
    if (!list.length) return null;
    if (preferredId) {
      const hit = list.find((c) => c.id === preferredId);
      if (hit) return hit;
    }
    const cached = this.getSelectedConnection();
    if (cached && list.some((c) => c.id === cached.id)) {
      return cached;
    }
    return list.find((c) => c.is_default) || list[0];
  }

  invalidate(environmentId?: string): void {
    if (environmentId) {
      this.allByEnv.delete(environmentId);
      this.databricksByEnv.delete(environmentId);
    } else {
      this.allByEnv.clear();
      this.databricksByEnv.clear();
    }
  }

  clearSelectedConnection(): void {
    this.selectedConnection$.next(null);
  }

  private storeAll(environmentId: string, list: EnvironmentConnection[]): void {
    this.allByEnv.set(environmentId, list);
    this.databricksByEnv.set(
      environmentId,
      list.filter((c) => c.connection_type === 'databricks')
    );
  }

  private mergeDatabricksIntoAll(environmentId: string, databricks: EnvironmentConnection[]): void {
    const existing = this.allByEnv.get(environmentId) || [];
    const byId = new Map(existing.map((c) => [c.id, c]));
    for (const c of databricks) {
      byId.set(c.id, c);
    }
    if (byId.size) {
      this.allByEnv.set(environmentId, Array.from(byId.values()));
    }
  }
}
