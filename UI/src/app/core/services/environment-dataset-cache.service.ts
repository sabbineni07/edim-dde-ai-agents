import { Injectable } from '@angular/core';
import { Observable, of, tap } from 'rxjs';
import { ApiService, EnvironmentDataset } from '../../services/api.service';

/** Schema profile used for Workspaces / Jobs / Runs browse (environment default). */
export const BROWSE_SCHEMA_PROFILE = 'job_inventory';

/** Browser-side cache for environment datasets (browse screens). */
@Injectable({ providedIn: 'root' })
export class EnvironmentDatasetCacheService {
  private byEnv = new Map<string, EnvironmentDataset[]>();

  constructor(private api: ApiService) {}

  getCached(environmentId: string): EnvironmentDataset[] | null {
    const eid = environmentId.trim();
    return eid && this.byEnv.has(eid) ? this.byEnv.get(eid)! : null;
  }

  getDatasets(environmentId: string, force = false): Observable<EnvironmentDataset[]> {
    const eid = environmentId.trim();
    if (!eid) return of([]);
    if (!force && this.byEnv.has(eid)) {
      return of(this.byEnv.get(eid)!);
    }
    return this.api.getEnvironmentDatasets(eid).pipe(tap((list) => this.byEnv.set(eid, list)));
  }

  /** Datasets suitable for Workspaces/Jobs/Runs browse pickers. */
  browseDatasets(list: EnvironmentDataset[]): EnvironmentDataset[] {
    return list.filter((d) => d.schema_profile === BROWSE_SCHEMA_PROFILE);
  }

  pickDataset(
    list: EnvironmentDataset[],
    preferredId: string | null
  ): EnvironmentDataset | null {
    const browse = this.browseDatasets(list);
    const pool = browse.length ? browse : [];
    if (!pool.length) return null;
    if (preferredId) {
      const hit = pool.find((d) => d.id === preferredId);
      if (hit) return hit;
    }
    return pool.find((d) => d.is_default) || pool[0];
  }

  invalidate(environmentId?: string): void {
    if (environmentId) {
      this.byEnv.delete(environmentId);
    } else {
      this.byEnv.clear();
    }
  }
}
