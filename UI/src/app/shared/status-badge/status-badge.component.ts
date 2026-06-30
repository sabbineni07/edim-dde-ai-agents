import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type StatusBadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  imports: [CommonModule],
  template: `<span class="status-badge" [ngClass]="'status-badge-' + variant">{{ label }}</span>`,
  styles: [
    `
      .status-badge {
        display: inline-block;
        font-size: var(--text-xs);
        font-weight: 600;
        padding: 0.1rem 0.35rem;
        border-radius: var(--radius-sm);
        line-height: 1.3;
        white-space: nowrap;
      }
      .status-badge-default {
        background: var(--color-surface-muted);
        color: var(--color-text);
        border: 1px solid var(--color-border-subtle);
      }
      .status-badge-success {
        background: rgba(25, 135, 84, 0.12);
        color: var(--color-success);
      }
      .status-badge-warning {
        background: rgba(184, 134, 11, 0.12);
        color: var(--color-warning);
      }
      .status-badge-danger {
        background: rgba(196, 30, 58, 0.1);
        color: var(--color-danger);
      }
      .status-badge-info {
        background: rgba(0, 102, 204, 0.1);
        color: var(--navy-accent);
      }
      .status-badge-secondary {
        background: var(--color-surface-muted);
        color: var(--color-text-muted);
      }
    `,
  ],
})
export class StatusBadgeComponent {
  @Input() label = '';
  @Input() variant: StatusBadgeVariant = 'default';
}
