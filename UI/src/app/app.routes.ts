import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', loadComponent: () => import('./features/login/login.component').then(m => m.LoginComponent) },
  {
    path: 'app',
    loadComponent: () => import('./layout/shell/shell.component').then(m => m.ShellComponent),
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'connections', pathMatch: 'full' },
      { path: 'environments', loadComponent: () => import('./features/environments/environments.component').then(m => m.EnvironmentsComponent) },
      { path: 'admin/environments', loadComponent: () => import('./features/manage-environments/manage-environments.component').then(m => m.ManageEnvironmentsComponent) },
      { path: 'connections', loadComponent: () => import('./features/connections/connections.component').then(m => m.ConnectionsComponent) },
      { path: 'datasets', loadComponent: () => import('./features/datasets/datasets.component').then(m => m.DatasetsComponent) },
      { path: 'workspaces', loadComponent: () => import('./features/workspaces/workspaces.component').then(m => m.WorkspacesComponent) },
      { path: 'workspaces/:workspaceId', loadComponent: () => import('./features/workspace-detail/workspace-detail.component').then(m => m.WorkspaceDetailComponent) },
      { path: 'jobs', loadComponent: () => import('./features/jobs/jobs-list.component').then(m => m.JobsListComponent) },
      { path: 'jobs/:workspaceId/:jobId', loadComponent: () => import('./features/job-detail/job-detail.component').then(m => m.JobDetailComponent) },
      { path: 'chat', loadComponent: () => import('./features/chat/chat.component').then(m => m.ChatComponent) },
      { path: 'agents', loadComponent: () => import('./features/agents/agents.component').then(m => m.AgentsComponent) },
      { path: 'agents/:agentId', loadComponent: () => import('./features/agent-detail/agent-detail.component').then(m => m.AgentDetailComponent) },
      { path: '**', redirectTo: 'connections' },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
