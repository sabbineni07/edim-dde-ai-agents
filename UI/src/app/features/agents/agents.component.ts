import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { AgentInfo, ApiService } from '../../services/api.service';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    PageHeaderComponent,
    LoadingCardComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
  ],
  templateUrl: './agents.component.html',
  styleUrls: ['./agents.component.css'],
})
export class AgentsComponent implements OnInit {
  agents: AgentInfo[] = [];
  loading = true;

  constructor(
    private api: ApiService,
    private router: Router,
    private workspaceSelection: WorkspaceSelectionService
  ) {}

  ngOnInit(): void {
    this.api.getAgents().subscribe({
      next: (res) => {
        this.agents = res.agents || [];
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  agentIcon(agentId: string): string {
    if (agentId.includes('cluster') || agentId.includes('tuning')) return 'bi-cpu';
    if (agentId.includes('cost')) return 'bi-currency-dollar';
    if (agentId.includes('chat')) return 'bi-chat-dots';
    return 'bi-robot';
  }

  agentCategory(agentId: string): string {
    if (agentId.includes('cluster') || agentId.includes('tuning')) return 'Cluster tuning';
    if (agentId.includes('cost')) return 'Cost optimization';
    return 'AI agent';
  }

  installInWorkspace(): void {
    const lastWs = this.workspaceSelection.getLastWorkspaceId();
    if (lastWs) {
      void this.router.navigate(['/app/workspaces', lastWs], { queryParams: { tab: 'agents' } });
      return;
    }
    void this.router.navigate(['/app/workspaces']);
  }
}
