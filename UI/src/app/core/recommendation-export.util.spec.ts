import {
  buildHistoryRecommendationExport,
  buildLatestRecommendationExport,
  recommendationExportFilename,
  recommendationExportJson,
} from './recommendation-export.util';

describe('recommendation-export.util', () => {
  it('builds latest recommendation export payload', () => {
    const payload = buildLatestRecommendationExport(
      {
        request_id: 'req-1',
        job_run_id: 'jr-001',
        cluster_id: 'run-001',
        recommendation: { num_workers: 4 },
        explanation: 'Scale down workers',
        reason_codes: ['LOW_CPU'],
        comparison: {
          current_configuration: { num_workers: 8 },
          recommended_configuration: { num_workers: 4 },
        },
      },
      { workspaceId: 'ws-1', jobId: 'job-001' }
    );

    expect(payload.workspace_id).toBe('ws-1');
    expect(payload.job_id).toBe('job-001');
    expect(payload.recommendation).toEqual({ num_workers: 4 });
    expect(payload.current_configuration).toEqual({ num_workers: 8 });
    expect(payload.recommended_configuration).toEqual({ num_workers: 4 });
    expect(payload.exported_at).toBeTruthy();
  });

  it('builds history recommendation export payload', () => {
    const payload = buildHistoryRecommendationExport({
      request_id: 'req-2',
      job_id: 'job-002',
      timestamp: '2026-06-01T12:00:00Z',
      recommendation: { driver_node_type: 'Standard_E8s_v3' },
      comparison: {
        current_configuration: { driver_node_type: 'Standard_E16s_v3' },
        recommended_configuration: { driver_node_type: 'Standard_E8s_v3' },
      },
    });

    expect(payload.job_id).toBe('job-002');
    expect(payload.timestamp).toBe('2026-06-01T12:00:00Z');
    expect(recommendationExportFilename(payload)).toBe(
      'recommendation-job-002-req-2.json'
    );
    expect(recommendationExportJson(payload)).toContain('"driver_node_type"');
  });
});
