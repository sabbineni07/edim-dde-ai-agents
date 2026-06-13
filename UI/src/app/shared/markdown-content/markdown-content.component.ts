import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

marked.setOptions({
  gfm: true,
  breaks: true,
});

@Component({
  selector: 'app-markdown-content',
  standalone: true,
  imports: [CommonModule],
  template: `<div class="markdown-body" [innerHTML]="rendered"></div>`,
  styleUrls: ['./markdown-content.component.css'],
})
export class MarkdownContentComponent implements OnChanges {
  @Input() content = '';

  rendered: SafeHtml = '';

  constructor(private sanitizer: DomSanitizer) {}

  ngOnChanges(changes: SimpleChanges): void {
    if ('content' in changes) {
      this.rendered = this.toSafeHtml(this.content);
    }
  }

  private toSafeHtml(raw: string): SafeHtml {
    const text = (raw || '').trim();
    if (!text) {
      return '';
    }
    const html = marked.parse(text, { async: false }) as string;
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
