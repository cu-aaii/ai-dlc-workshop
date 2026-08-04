import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { MastheadComponent } from './shared/layout/masthead/masthead.component';
import { MainMenuComponent } from './shared/layout/main-menu/main-menu.component';
import { MainComponent } from './shared/layout/main/main.component';
import { FooterComponent } from './shared/layout/footer/footer.component';
import { AppRoute, routes } from './app.routes';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    MastheadComponent,
    MainMenuComponent,
    MainComponent,
    FooterComponent,
  ],
  template: `
    <lib-masthead />
    <lib-main-menu [routes]="navRoutes" />
    <lib-main>
      <router-outlet />
    </lib-main>
    <lib-footer />
  `,
  styles: `
    :host { display: block; min-height: 100vh; }
  `,
})
export class AppComponent {
  navRoutes: AppRoute[] = routes.filter((r) => r.data.menu.includes('main'));
}
