import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { distinctUntilChanged, map } from 'rxjs/operators';
import { ApiService, EnvironmentConnection, PlatformEnvironment } from '../../services/api.service';
import { BrowseDataCacheService } from './browse-data-cache.service';
import { EnvironmentConnectionCacheService } from './environment-connection-cache.service';

const ENV_KEY = 'edim_selected_environment_id';
const ENV_NAME_KEY = 'edim_selected_environment_name';
const CONN_KEY = 'edim_selected_connection_id';
const LEGACY_CONN_KEY = 'edim_selected_metrics_connection_id';

export interface SelectedEnvironment {
  id: string;
  displayName: string;
}

function readStoredConnectionId(): string | null {
  try {
    return (
      localStorage.getItem(CONN_KEY)?.trim() ||
      localStorage.getItem(LEGACY_CONN_KEY)?.trim() ||
      null
    );
  } catch {
    return null;
  }
}

/**
 * Session context: environment slug (e.g. dim_dev) and selected Databricks connection UUID.
 *
 * Environment ids are stable business keys from platform seed (Unity Catalog scope),
 * not auto-generated UUIDs. Connection rows use UUID primary keys.
 */
@Injectable({ providedIn: 'root' })
export class EnvironmentSelectionService {
  private environments$ = new BehaviorSubject<PlatformEnvironment[]>([]);
  private selected$ = new BehaviorSubject<SelectedEnvironment | null>(this.getSelected());
  private selectedConnectionId$ = new BehaviorSubject<string | null>(readStoredConnectionId());

  constructor(
    private api: ApiService,
    private connectionCache: EnvironmentConnectionCacheService,
    private browseCache: BrowseDataCacheService
  ) {}

  watchEnvironments(): Observable<PlatformEnvironment[]> {
    return this.environments$.asObservable();
  }

  watchSelected(): Observable<SelectedEnvironment | null> {
    return this.selected$.asObservable();
  }

  /** Emits only when the environment id changes (avoids duplicate page loads). */
  watchSelectedId(): Observable<string | null> {
    return this.selected$.pipe(
      map((s) => s?.id ?? null),
      distinctUntilChanged()
    );
  }

  watchSelectedConnectionId(): Observable<string | null> {
    return this.selectedConnectionId$.asObservable();
  }

  watchSelectedConnection(): Observable<EnvironmentConnection | null> {
    return this.connectionCache.watchSelectedConnection();
  }

  getSelected(): SelectedEnvironment | null {
    try {
      const id = localStorage.getItem(ENV_KEY)?.trim();
      if (!id) return null;
      const displayName = localStorage.getItem(ENV_NAME_KEY)?.trim() || id;
      return { id, displayName };
    } catch {
      return null;
    }
  }

  getSelectedId(): string | null {
    return this.getSelected()?.id ?? null;
  }

  getSelectedConnectionId(): string | null {
    return (
      this.connectionCache.getSelectedConnection()?.id ||
      readStoredConnectionId()
    );
  }

  getSelectedConnection(): EnvironmentConnection | null {
    return this.connectionCache.getSelectedConnection();
  }

  setSelected(environment: SelectedEnvironment): void {
    const prevId = this.getSelectedId();
    const nextId = environment.id.trim();
    try {
      localStorage.setItem(ENV_KEY, nextId);
      localStorage.setItem(ENV_NAME_KEY, environment.displayName.trim());
      this.selected$.next(environment);
      if (prevId !== nextId) {
        this.connectionCache.clearSelectedConnection();
        this.persistConnectionId(null);
        if (prevId) {
          this.browseCache.invalidateEnvironment(prevId);
        }
        this.browseCache.invalidateEnvironment(nextId);
      }
    } catch {
      // ignore storage errors
    }
  }

  setSelectedConnection(connection: EnvironmentConnection | null): void {
    const prevConnId = this.getSelectedConnectionId();
    const nextConnId = connection?.id?.trim() || null;
    this.connectionCache.setSelectedConnection(connection);
    this.persistConnectionId(connection?.id ?? null);
    const envId = this.getSelectedId();
    if (envId && prevConnId !== nextConnId) {
      this.browseCache.invalidateEnvironment(envId);
    }
  }

  private persistConnectionId(connectionId: string | null): void {
    try {
      if (connectionId?.trim()) {
        localStorage.setItem(CONN_KEY, connectionId.trim());
      } else {
        localStorage.removeItem(CONN_KEY);
      }
      localStorage.removeItem(LEGACY_CONN_KEY);
      this.selectedConnectionId$.next(connectionId?.trim() || null);
    } catch {
      // ignore
    }
  }

  invalidateConnectionCache(environmentId?: string): void {
    this.connectionCache.invalidate(environmentId);
    if (environmentId) {
      this.browseCache.invalidateEnvironment(environmentId);
    } else {
      this.browseCache.clear();
    }
  }

  clearSelected(): void {
    try {
      localStorage.removeItem(ENV_KEY);
      localStorage.removeItem(ENV_NAME_KEY);
      localStorage.removeItem(CONN_KEY);
      localStorage.removeItem(LEGACY_CONN_KEY);
      this.selected$.next(null);
      this.selectedConnectionId$.next(null);
      this.connectionCache.clearSelectedConnection();
      this.connectionCache.invalidate();
      this.browseCache.clear();
    } catch {
      // ignore
    }
  }

  loadEnvironments(): Observable<PlatformEnvironment[]> {
    return new Observable((subscriber) => {
      this.api.getEnvironments().subscribe({
        next: (list) => {
          this.environments$.next(list);
          const stored = this.getSelected();
          const validStored = stored && list.some((e) => e.id === stored.id && e.is_enabled !== false);
          if (!validStored && list.length) {
            const pick =
              list.find((e) => e.id === 'dim_dev' && e.is_enabled !== false) ||
              list.find((e) => e.is_enabled !== false);
            if (pick) {
              this.setSelected({ id: pick.id, displayName: pick.display_name });
            }
          } else if (validStored && stored) {
            const env = list.find((e) => e.id === stored.id);
            if (env && env.display_name !== stored.displayName) {
              this.setSelected({ id: env.id, displayName: env.display_name });
            }
          }
          subscriber.next(list);
          subscriber.complete();
        },
        error: (err) => subscriber.error(err),
      });
    });
  }
}
