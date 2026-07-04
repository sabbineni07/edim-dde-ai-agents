import {
  Component,
  ElementRef,
  HostListener,
  Input,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';

const PANEL_WIDTH = 352;
const VIEWPORT_MARGIN = 12;

@Component({
  selector: 'app-content-help',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './content-help.component.html',
  styleUrls: ['./content-help.component.css'],
  host: {
    class: 'content-help-host',
  },
})
export class ContentHelpComponent {
  @Input() summary = '';
  @Input() detail = '';
  @Input() backendRef = '';
  @Input() label = 'Usage information';

  @ViewChild('trigger') triggerRef?: ElementRef<HTMLButtonElement>;

  open = false;
  panelStyle: Record<string, string> = {};

  toggle(event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.open = !this.open;
    if (this.open) {
      requestAnimationFrame(() => this.positionPanel());
    }
  }

  close(): void {
    this.open = false;
  }

  private positionPanel(): void {
    const trigger = this.triggerRef?.nativeElement;
    if (!trigger) {
      return;
    }

    const rect = trigger.getBoundingClientRect();
    const maxWidth = Math.min(PANEL_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);
    let left = rect.left;
    if (left + maxWidth > window.innerWidth - VIEWPORT_MARGIN) {
      left = window.innerWidth - maxWidth - VIEWPORT_MARGIN;
    }
    left = Math.max(VIEWPORT_MARGIN, left);

    let top = rect.bottom + 8;
    const estimatedHeight = 160;
    if (top + estimatedHeight > window.innerHeight - VIEWPORT_MARGIN) {
      top = Math.max(VIEWPORT_MARGIN, rect.top - estimatedHeight - 8);
    }

    this.panelStyle = {
      top: `${top}px`,
      left: `${left}px`,
      width: `${maxWidth}px`,
    };
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.open = false;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.open = false;
  }

  @HostListener('window:resize')
  onResize(): void {
    if (this.open) {
      this.positionPanel();
    }
  }

  @HostListener('window:scroll')
  onScroll(): void {
    if (this.open) {
      this.positionPanel();
    }
  }
}
