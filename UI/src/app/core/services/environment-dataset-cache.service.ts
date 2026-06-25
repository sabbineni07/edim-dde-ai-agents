import { Injectable } from '@angular/core';
import { Observable, of, tap } from 'rxjs';
import { ApiService, EnvironmentDataset } from '../../services/api.service';

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

  pickDataset(
    list: EnvironmentDataset[],
    preferredId: string | null
  ): EnvironmentDataset | null {
    if (!list.length) return null;
    if (preferredId) {
      const hit = list.find((d) => d.id === preferredId);
      if (hit) return hit;
    }
    return list.find((d) => d.is_default) || list[0];
  }

  invalidate(environmentId?: string): void {
    if (environmentId) {
      this.byEnv.delete(environmentId);
    } else {
      this.byEnv.clear();
    }
  }
}
