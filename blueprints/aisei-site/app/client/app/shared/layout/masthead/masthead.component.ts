import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'lib-masthead',
  imports: [RouterLink],
  template: `
    <div class="cu-masthead">
      <div class="container-fluid">
        <div class="masthead-inner">
          <a class="brand" routerLink="/">
            <small>Cornell University</small>
            <strong>AI Innovation Hub</strong>
          </a>
          <img class="seal" src="assets/cornell_seal.svg" alt="Cornell University seal">
        </div>
      </div>
    </div>
  `,
  styleUrls: ['./masthead.component.scss'],
})
export class MastheadComponent {}
