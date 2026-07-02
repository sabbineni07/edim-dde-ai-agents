import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  AgentChainUsage,
  AgentContentResponse,
  AgentContentVersionSummary,
  AgentPromptContent,
  AgentSkillContent,
  ApiService,
} from '../../services/api.service';
import { parseApiError } from '../../core/api-error.util';
import { ToastService } from '../../core/services/toast.service';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { MarkdownContentComponent } from '../../shared/markdown-content/markdown-content.component';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import { ContentHelpComponent } from '../../shared/content-help/content-help.component';
import { BreadcrumbItem } from '../../shared/breadcrumb/breadcrumb.component';

type ContentTab = 'prompts' | 'skills';

interface HistoryTarget {
  kind: 'prompt' | 'skill';
  label: string;
  chainName?: string;
  role?: string;
  skillKey?: string;
}

@Component({
  selector: 'app-agent-detail',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    PageHeaderComponent,
    LoadingCardComponent,
    EmptyStateComponent,
    MarkdownContentComponent,
    StatusBadgeComponent,
    ContentHelpComponent,
  ],
  templateUrl: './agent-detail.component.html',
  styleUrls: ['./agent-detail.component.css'],
})
export class AgentDetailComponent implements OnInit {
  agentId = '';
  content: AgentContentResponse | null = null;
  loading = true;
  error = '';
  activeTab: ContentTab = 'prompts';

  editingPromptKey: string | null = null;
  editingSkillKey: string | null = null;
  draftContent = '';
  saveError = '';
  saving = false;
  resetting = false;
  showResetConfirm = false;

  historyTarget: HistoryTarget | null = null;
  historyVersions: AgentContentVersionSummary[] = [];
  historyLoading = false;
  historyError = '';
  diffFromVersion: number | null = null;
  diffToVersion: number | null = null;
  diffText = '';
  diffLoading = false;
  diffError = '';

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.agentId = this.route.snapshot.paramMap.get('agentId') || '';
    if (!this.agentId) {
      this.loading = false;
      this.error = 'Missing agent id';
      return;
    }
    this.loadContent();
  }

  private loadContent(): void {
    this.loading = true;
    this.error = '';
    this.api.getAgentContent(this.agentId).subscribe({
      next: (res) => {
        this.content = res;
        this.loading = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to load agent content';
        this.loading = false;
      },
    });
  }

  setTab(tab: ContentTab): void {
    this.activeTab = tab;
    this.cancelEdit();
    this.closeHistory();
  }

  promptKey(chainName: string, role: string): string {
    return `${chainName}::${role}`;
  }

  isEditingPrompt(chainName: string, role: string): boolean {
    return this.editingPromptKey === this.promptKey(chainName, role);
  }

  isEditingSkill(skillKey: string): boolean {
    return this.editingSkillKey === skillKey;
  }

  startEditPrompt(prompt: AgentPromptContent): void {
    if (!this.content?.can_edit) {
      return;
    }
    this.closeHistory();
    this.editingSkillKey = null;
    this.editingPromptKey = this.promptKey(prompt.chain_name, prompt.role);
    this.draftContent = prompt.content;
    this.saveError = '';
  }

  startEditSkill(skill: AgentSkillContent): void {
    if (!this.content?.can_edit) {
      return;
    }
    this.closeHistory();
    this.editingPromptKey = null;
    this.editingSkillKey = skill.skill_key;
    this.draftContent = skill.content;
    this.saveError = '';
  }

  cancelEdit(): void {
    this.editingPromptKey = null;
    this.editingSkillKey = null;
    this.draftContent = '';
    this.saveError = '';
    this.saving = false;
  }

  savePromptEdit(prompt: AgentPromptContent): void {
    if (!this.content || this.saving) {
      return;
    }
    this.saving = true;
    this.saveError = '';
    this.api
      .updateAgentPrompt(this.agentId, prompt.chain_name, prompt.role, this.draftContent)
      .subscribe({
        next: (updated) => {
          this.applyPromptUpdate(updated);
          this.cancelEdit();
          this.toast.success('Prompt saved');
        },
        error: (err) => {
          this.saveError = parseApiError(err, 'Failed to save prompt');
          this.saving = false;
        },
      });
  }

  saveSkillEdit(skill: AgentSkillContent): void {
    if (!this.content || this.saving) {
      return;
    }
    this.saving = true;
    this.saveError = '';
    this.api
      .updateAgentSkill(this.agentId, skill.skill_key, { content: this.draftContent })
      .subscribe({
        next: (updated) => {
          this.applySkillUpdate(updated);
          this.cancelEdit();
          this.toast.success('Skill saved');
        },
        error: (err) => {
          this.saveError = parseApiError(err, 'Failed to save skill');
          this.saving = false;
        },
      });
  }

  openPromptHistory(prompt: AgentPromptContent): void {
    this.cancelEdit();
    this.historyTarget = {
      kind: 'prompt',
      label: `${this.chainLabel(prompt.chain_name)} / ${prompt.role}`,
      chainName: prompt.chain_name,
      role: prompt.role,
    };
    this.loadHistory();
  }

  openSkillHistory(skill: AgentSkillContent): void {
    this.cancelEdit();
    this.historyTarget = {
      kind: 'skill',
      label: skill.title,
      skillKey: skill.skill_key,
    };
    this.loadHistory();
  }

  closeHistory(): void {
    this.historyTarget = null;
    this.historyVersions = [];
    this.historyLoading = false;
    this.historyError = '';
    this.diffFromVersion = null;
    this.diffToVersion = null;
    this.diffText = '';
    this.diffLoading = false;
    this.diffError = '';
  }

  private loadHistory(): void {
    if (!this.historyTarget) {
      return;
    }
    this.historyLoading = true;
    this.historyError = '';
    this.diffText = '';
    this.diffError = '';

    const req =
      this.historyTarget.kind === 'prompt'
        ? this.api.listAgentPromptVersions(
            this.agentId,
            this.historyTarget.chainName!,
            this.historyTarget.role!
          )
        : this.api.listAgentSkillVersions(this.agentId, this.historyTarget.skillKey!);

    req.subscribe({
      next: (res) => {
        this.historyVersions = res.versions || [];
        this.historyLoading = false;
        if (this.historyVersions.length >= 2) {
          this.diffToVersion = this.historyVersions[0].version;
          this.diffFromVersion = this.historyVersions[1].version;
        } else if (this.historyVersions.length === 1) {
          this.diffToVersion = this.historyVersions[0].version;
          this.diffFromVersion = this.historyVersions[0].version;
        }
      },
      error: (err) => {
        this.historyError = parseApiError(err, 'Failed to load version history');
        this.historyLoading = false;
      },
    });
  }

  compareVersions(): void {
    if (!this.historyTarget || this.diffFromVersion == null || this.diffToVersion == null) {
      return;
    }
    if (this.diffFromVersion === this.diffToVersion) {
      this.diffError = 'Choose two different versions to compare.';
      this.diffText = '';
      return;
    }
    this.diffLoading = true;
    this.diffError = '';
    const req =
      this.historyTarget.kind === 'prompt'
        ? this.api.diffAgentPromptVersions(
            this.agentId,
            this.historyTarget.chainName!,
            this.historyTarget.role!,
            this.diffFromVersion,
            this.diffToVersion
          )
        : this.api.diffAgentSkillVersions(
            this.agentId,
            this.historyTarget.skillKey!,
            this.diffFromVersion,
            this.diffToVersion
          );

    req.subscribe({
      next: (res) => {
        this.diffText = res.diff;
        this.diffLoading = false;
      },
      error: (err) => {
        this.diffError = parseApiError(err, 'Failed to load diff');
        this.diffLoading = false;
      },
    });
  }

  confirmReset(): void {
    this.showResetConfirm = true;
  }

  cancelReset(): void {
    this.showResetConfirm = false;
  }

  resetToSeed(): void {
    if (!this.content?.can_edit || this.resetting) {
      return;
    }
    this.resetting = true;
    this.api.resetAgentContent(this.agentId).subscribe({
      next: (res) => {
        this.content = res.content;
        this.showResetConfirm = false;
        this.resetting = false;
        this.closeHistory();
        this.cancelEdit();
        const total = res.prompts_reset + res.skills_reset;
        if (total > 0) {
          this.toast.success(`Restored ${total} item(s) to seed defaults`);
        } else {
          this.toast.success('Content already matches seed defaults');
        }
      },
      error: (err) => {
        this.resetting = false;
        this.toast.error(parseApiError(err, 'Failed to reset content'));
      },
    });
  }

  private applyPromptUpdate(updated: AgentPromptContent): void {
    if (!this.content) {
      return;
    }
    const idx = this.content.prompts.findIndex(
      (p) => p.chain_name === updated.chain_name && p.role === updated.role
    );
    if (idx >= 0) {
      this.content.prompts[idx] = updated;
    }
  }

  private applySkillUpdate(updated: AgentSkillContent): void {
    if (!this.content) {
      return;
    }
    const idx = this.content.skills.findIndex((s) => s.skill_key === updated.skill_key);
    if (idx >= 0) {
      this.content.skills[idx] = updated;
    }
  }

  chainLabel(chainName: string): string {
    return chainName.replace(/_/g, ' ');
  }

  chainUsage(chainName: string): AgentChainUsage | null {
    return this.content?.chain_usage?.[chainName] ?? null;
  }

  hasUsage(item: { usage_summary?: string | null; usage_detail?: string | null }): boolean {
    return Boolean(item.usage_summary && item.usage_detail);
  }

  promptsForChain(chainName: string): AgentPromptContent[] {
    return (this.content?.prompts || []).filter((p) => p.chain_name === chainName);
  }

  get promptChains(): string[] {
    const names = new Set((this.content?.prompts || []).map((p) => p.chain_name));
    return Array.from(names);
  }

  get breadcrumbs(): BreadcrumbItem[] {
    return [
      { label: 'Agents', link: '/app/agents' },
      { label: this.content?.definition.display_name || this.agentId },
    ];
  }

  get pageTitle(): string {
    return this.content?.definition.display_name || this.agentId;
  }

  get pageSubtitle(): string {
    return this.content?.definition.description || 'Agent instructions, prompts, and skills';
  }
}
