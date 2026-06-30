import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-loading-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './loading-card.component.html',
  styleUrls: ['./loading-card.component.css'],
})
export class LoadingCardComponent {
  @Input() message = 'Loading…';
  @Input() variant: 'spinner' | 'skeleton' = 'spinner';
  @Input() skeletonRows = 5;
  @Input() compact = true;

  rowIndices(): number[] {
    return Array.from({ length: this.skeletonRows }, (_, i) => i);
  }
}
