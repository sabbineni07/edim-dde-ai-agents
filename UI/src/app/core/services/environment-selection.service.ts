import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { distinctUntilChanged, map } from 'rxjs/operators';
import { ApiService, EnvironmentConnection, PlatformEnvironment } from '../../services/api.service';
import { AuthService } from './auth.service';
import { BrowseDataCacheService } from './browse-data-cache.service';
import { EnvironmentConnectionCacheService } from './environment-connection-cache.service';

/** Legacy global keys (migrated to per-user keys on first read). */
const LEGACY_ENV_KEY = 'edim_selected_environment_id';
const LEGACY_ENV_NAME_KEY = 'edim_selected_environment_name';
const LEGACY_CONN_KEY = 'edim_selected_connection_id';
const LEGACY_DATASET_KEY = 'edim_selected_dataset_id';
const LEGACY_METRICS_CONN_KEY = 'edim_selected_metrics_connection_id';

export interface SelectedEnvironment {
  id: string;
  displayName: string;
}

interface UserStorageKeys {
  env: string;
  envName: string;
  conn: string;
  dataset: string;
}

/**
 * Session context: environment slug (e.g. dim_dev) and selected Databricks connection UUID.
 *
 * Preferences are persisted in localStorage per signed-in user and restored on login.
 */
@Injectable({ providedIn: 'root' })
export class EnvironmentSelectionService {
  private environments$ = new BehaviorSubject<PlatformEnvironment[]>([]);
  private selected$ = new BehaviorSubject<SelectedEnvironment | null>(null);
  private selectedConnectionId$ = new BehaviorSubject<string | null>(null);
  private selectedDatasetId$ = new BehaviorSubject<string | null>(null);

  constructor(
    private api: ApiService,
    private auth: AuthService,
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

  watchSelectedDatasetId(): Observable<string | null> {
    return this.selectedDatasetId$.asObservable();
  }

  watchSelectedConnection(): Observable<EnvironmentConnection | null> {
    return this.connectionCache.watchSelectedConnection();
  }

  /** Load persisted prefs for the current user into in-memory state (call after login). */
  initializeForCurrentUser(): void {
    this.migrateLegacyStorage();
    const stored = this.getSelected();
    this.selected$.next(stored);
    this.selectedConnectionId$.next(this.readStoredConnectionId());
    this.selectedDatasetId$.next(this.readStoredDatasetId());
  }

  /** Latest loaded environment row for the given id (from header env list). */
  getEnvironmentRecord(environmentId: string): PlatformEnvironment | null {
    const id = environmentId?.trim();
    if (!id) return null;
    return this.environments$.value.find((e) => e.id === id) ?? null;
  }

  getSelected(): SelectedEnvironment | null {
    try {
      const keys = this.storageKeys();
      const id = localStorage.getItem(keys.env)?.trim();
      if (!id) return null;
      const displayName = localStorage.getItem(keys.envName)?.trim() || id;
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
      this.readStoredConnectionId()
    );
  }

  getSelectedConnection(): EnvironmentConnection | null {
    return this.connectionCache.getSelectedConnection();
  }

  getSelectedDatasetId(): string | null {
    return this.readStoredDatasetId();
  }

  setSelected(environment: SelectedEnvironment): void {
    const prevId = this.getSelectedId();
    const nextId = environment.id.trim();
    try {
      const keys = this.storageKeys();
      localStorage.setItem(keys.env, nextId);
      localStorage.setItem(keys.envName, environment.displayName.trim());
      this.selected$.next(environment);
      if (prevId !== nextId) {
        this.connectionCache.clearSelectedConnection();
        this.persistConnectionId(null);
        this.persistDatasetId(null);
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

  setSelectedDataset(datasetId: string | null): void {
    const prevDatasetId = this.getSelectedDatasetId();
    const nextDatasetId = datasetId?.trim() || null;
    this.persistDatasetId(nextDatasetId);
    const envId = this.getSelectedId();
    if (envId && prevDatasetId !== nextDatasetId) {
      this.browseCache.invalidateEnvironment(envId);
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

  /** Clear in-memory session state only (logout). Persisted prefs are kept for next login. */
  clearSession(): void {
    this.selected$.next(null);
    this.selectedConnectionId$.next(null);
    this.selectedDatasetId$.next(null);
    this.connectionCache.clearSelectedConnection();
    this.connectionCache.invalidate();
    this.browseCache.clear();
  }

  /** Remove persisted preferences for the current user. */
  clearSelected(): void {
    try {
      const keys = this.storageKeys();
      localStorage.removeItem(keys.env);
      localStorage.removeItem(keys.envName);
      localStorage.removeItem(keys.conn);
      localStorage.removeItem(keys.dataset);
      this.clearSession();
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
            } else {
              this.selected$.next(stored);
            }
          }
          subscriber.next(list);
          subscriber.complete();
        },
        error: (err) => subscriber.error(err),
      });
    });
  }

  private storageKeys(): UserStorageKeys {
    const user = (this.auth.currentUser?.username || '_anonymous').trim().toLowerCase();
    return {
      env: `edim_selected_environment_id:${user}`,
      envName: `edim_selected_environment_name:${user}`,
      conn: `edim_selected_connection_id:${user}`,
      dataset: `edim_selected_dataset_id:${user}`,
    };
  }

  private readStoredConnectionId(): string | null {
    try {
      const keys = this.storageKeys();
      return (
        localStorage.getItem(keys.conn)?.trim() ||
        localStorage.getItem(LEGACY_METRICS_CONN_KEY)?.trim() ||
        null
      );
    } catch {
      return null;
    }
  }

  private readStoredDatasetId(): string | null {
    try {
      const keys = this.storageKeys();
      return localStorage.getItem(keys.dataset)?.trim() || null;
    } catch {
      return null;
    }
  }

  private persistConnectionId(connectionId: string | null): void {
    try {
      const keys = this.storageKeys();
      if (connectionId?.trim()) {
        localStorage.setItem(keys.conn, connectionId.trim());
      } else {
        localStorage.removeItem(keys.conn);
      }
      this.selectedConnectionId$.next(connectionId?.trim() || null);
    } catch {
      // ignore
    }
  }

  private persistDatasetId(datasetId: string | null): void {
    try {
      const keys = this.storageKeys();
      if (datasetId?.trim()) {
        localStorage.setItem(keys.dataset, datasetId.trim());
      } else {
        localStorage.removeItem(keys.dataset);
      }
      this.selectedDatasetId$.next(datasetId?.trim() || null);
    } catch {
      // ignore
    }
  }

  /** One-time migration from pre-login global localStorage keys. */
  private migrateLegacyStorage(): void {
    try {
      const keys = this.storageKeys();
      if (localStorage.getItem(keys.env)) {
        return;
      }
      const legacyEnv = localStorage.getItem(LEGACY_ENV_KEY)?.trim();
      if (!legacyEnv) {
        return;
      }
      localStorage.setItem(keys.env, legacyEnv);
      const legacyName = localStorage.getItem(LEGACY_ENV_NAME_KEY)?.trim();
      if (legacyName) {
        localStorage.setItem(keys.envName, legacyName);
      }
      const legacyConn =
        localStorage.getItem(LEGACY_CONN_KEY)?.trim() ||
        localStorage.getItem(LEGACY_METRICS_CONN_KEY)?.trim();
      if (legacyConn) {
        localStorage.setItem(keys.conn, legacyConn);
      }
      const legacyDataset = localStorage.getItem(LEGACY_DATASET_KEY)?.trim();
      if (legacyDataset) {
        localStorage.setItem(keys.dataset, legacyDataset);
      }
      localStorage.removeItem(LEGACY_ENV_KEY);
      localStorage.removeItem(LEGACY_ENV_NAME_KEY);
      localStorage.removeItem(LEGACY_CONN_KEY);
      localStorage.removeItem(LEGACY_DATASET_KEY);
      localStorage.removeItem(LEGACY_METRICS_CONN_KEY);
    } catch {
      // ignore
    }
  }
}
