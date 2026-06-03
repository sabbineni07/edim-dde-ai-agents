import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { AgentInfo, ApiService } from '../../services/api.service';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, RouterLink],
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
