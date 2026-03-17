import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
})
export class LoginComponent {
  form: FormGroup;
  submitted = false;
  error = '';
  loading = false;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private auth: AuthService
  ) {
    this.form = this.fb.group({
      username: ['', Validators.required],
      password: ['', [Validators.required, Validators.minLength(4)]],
    });
  }

  get f() {
    return this.form.controls;
  }

  onSubmit(): void {
    this.submitted = true;
    this.error = '';
    if (this.form.invalid) return;

    this.loading = true;
    this.auth
      .login(this.form.value.username, this.form.value.password)
      .then(() => {
        this.loading = false;
        this.router.navigate(['/app/workspaces']);
      })
      .catch((err) => {
        this.loading = false;
        this.error = err?.message || 'Login failed.';
      });
  }
}
