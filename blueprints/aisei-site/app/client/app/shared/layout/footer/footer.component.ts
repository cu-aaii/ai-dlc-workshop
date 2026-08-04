import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'lib-footer',
  imports: [RouterLink],
  template: `
    <footer class="site-footer">
      <div class="footer-cols">
        <div class="footer-org">
          <strong>AI Innovation Hub</strong>
          Bowers College of Computing and Information Science Building<br />
          127 Hoy Rd., Room 245<br />
          Ithaca, NY 14850
          <a class="btn-contact" href="#">Contact Us</a>
        </div>
        <div>
          <h4>Explore this demo</h4>
          <ul>
            <li><a routerLink="/">Home</a></li>
            <li><a routerLink="/component-library">Component Library</a></li>
            <li><a routerLink="/style-guide">Style Guide</a></li>
            <li><a routerLink="/implementation-plan">Implementation Plan</a></li>
          </ul>
        </div>
        <div>
          <h4>About</h4>
          <p>
            A demo rebuild of the AI Innovation Hub site's public look, scoped to a
            landing page and design reference. Part of the
            <a href="https://innovationhub.ai.cornell.edu/" target="_blank" rel="noopener">Cornell AI Initiative</a>.
          </p>
        </div>
      </div>
      <div class="footer-legal">
        <span>Cornell University &copy; 2026</span>
        <span><a href="#">University Privacy</a> &middot; <a href="#">Web Accessibility Assistance</a></span>
      </div>
    </footer>
  `,
  styleUrls: ['./footer.component.scss'],
})
export class FooterComponent {}
