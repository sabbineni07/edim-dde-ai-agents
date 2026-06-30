import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  PlatformEnvironment,
  PlatformEnvironmentUpdate,
} from '../../services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';

@Component({
  selector: 'app-manage-environments',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PageHeaderComponent, LoadingCardComponent],
  templateUrl: './manage-environments.component.html',
  styleUrls: ['./manage-environments.component.css'],
})
export class ManageEnvironmentsComponent implements OnInit {
  environments: PlatformEnvironment[] = [];
  loading = true;
  error = '';
  editing: PlatformEnvironment | null = null;
  editForm: PlatformEnvironmentUpdate = {};
  saving = false;
  saveError = '';

  constructor(
    private api: ApiService,
    private auth: AuthService,
    private router: Router
  ) {}

  ngOnInit(): void {
    if (!this.auth.isAdmin()) {
      void this.router.navigate(['/app/workspaces']);
      return;
    }
    this.load();
  }

  load(): void {
    this.loading = true;
    this.api.getEnvironments().subscribe({
      next: (list) => {
        this.environments = list;
        this.loading = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'Failed to load environments');
        this.loading = false;
      },
    });
  }

  openEdit(env: PlatformEnvironment): void {
    this.editing = env;
    this.saveError = '';
    this.editForm = {
      display_name: env.display_name,
      description: env.description,
      environment_tier: env.environment_tier,
      sort_order: env.sort_order,
      icon: env.icon,
      is_enabled: env.is_enabled !== false,
    };
  }

  closeEdit(): void {
    this.editing = null;
  }

  saveEdit(): void {
    if (!this.editing) return;
    this.saving = true;
    this.saveError = '';
    this.api.updateEnvironment(this.editing.id, this.editForm).subscribe({
      next: () => {
        this.saving = false;
        this.closeEdit();
        this.load();
      },
      error: (err) => {
        this.saving = false;
        this.saveError = parseApiError(err, 'Save failed');
      },
    });
  }
}
