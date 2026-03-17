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
      { path: '', redirectTo: 'workspaces', pathMatch: 'full' },
      { path: 'workspaces', loadComponent: () => import('./features/workspaces/workspaces.component').then(m => m.WorkspacesComponent) },
      { path: 'jobs', loadComponent: () => import('./features/jobs/jobs-list.component').then(m => m.JobsListComponent) },
      { path: 'jobs/:workspaceId/:jobId', loadComponent: () => import('./features/job-detail/job-detail.component').then(m => m.JobDetailComponent) },
      { path: 'chat', loadComponent: () => import('./features/chat/chat.component').then(m => m.ChatComponent) },
      { path: 'agents', loadComponent: () => import('./features/agents/agents.component').then(m => m.AgentsComponent) },
      { path: '**', redirectTo: 'workspaces' },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
