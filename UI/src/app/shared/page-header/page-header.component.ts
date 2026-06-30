import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BreadcrumbComponent, BreadcrumbItem } from '../breadcrumb/breadcrumb.component';

@Component({
  selector: 'app-page-header',
  standalone: true,
  imports: [CommonModule, BreadcrumbComponent],
  templateUrl: './page-header.component.html',
  styleUrls: ['./page-header.component.css'],
})
export class PageHeaderComponent {
  @Input() title = '';
  @Input() icon = '';
  @Input() subtitle = '';
  @Input() breadcrumbs: BreadcrumbItem[] = [];
  @Input() compact = true;

  get iconClass(): string {
    return this.icon ? `bi bi-${this.icon}` : '';
  }
}
