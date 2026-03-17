import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

interface AgentCard {
  id: string;
  name: string;
  description: string;
  howToUse: string;
  getStartedRoute: string;
  icon: string;
}

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './agents.component.html',
  styleUrls: ['./agents.component.css'],
})
export class AgentsComponent {
  agents: AgentCard[] = [
    {
      id: 'cluster-recommender',
      name: 'Cluster config recommender',
      description: 'Recommends node type and min/max workers from your job’s utilization and pattern analysis.',
      howToUse: 'Pick a workspace and job, open job details, then click "Run recommendation".',
      getStartedRoute: '/app/workspaces',
      icon: 'bi-cpu',
    },
    {
      id: 'metrics-chat',
      name: 'Metrics chat',
      description: 'Ask questions about your job cost and cluster metrics. You can scope by workspace and job or ask across all data.',
      howToUse: 'Open Chat, optionally set workspace/job, then type your question.',
      getStartedRoute: '/app/chat',
      icon: 'bi-chat-dots',
    },
  ];
}
