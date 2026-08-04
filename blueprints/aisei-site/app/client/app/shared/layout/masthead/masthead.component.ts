import { Component } from '@angular/core';

@Component({
  selector: 'lib-masthead',
  imports: [],
  template: `
    <div class="cu-utility-bar">
      <span aria-hidden="true">&#128269;</span>
      <span>Search</span>
    </div>
    <div class="cu-masthead">
      <div class="brand">
        <small>Cornell University</small>
        <strong>AI Innovation Hub</strong>
      </div>
      <img class="seal" src="assets/cornell_seal.svg" alt="Cornell University seal">
    </div>
  `,
  styleUrls: ['./masthead.component.scss'],
})
export class MastheadComponent {}
