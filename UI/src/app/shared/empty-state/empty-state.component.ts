import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './empty-state.component.html',
  styleUrls: ['./empty-state.component.css'],
})
export class EmptyStateComponent {
  @Input() icon = 'inbox';
  @Input() title = 'No data';
  @Input() description = '';
  @Input() actionLabel = '';
  @Input() actionLink: string | unknown[] = '';
  @Input() compact = true;
}
