import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { AgentInfo, ApiService } from '../../services/api.service';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, RouterLink, PageHeaderComponent, LoadingCardComponent, EmptyStateComponent],
  templateUrl: './agents.component.html',
  styleUrls: ['./agents.component.css'],
})
export class AgentsComponent implements OnInit {
  agents: AgentInfo[] = [];
  loading = true;

  constructor(private api: ApiService) {}

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
}
