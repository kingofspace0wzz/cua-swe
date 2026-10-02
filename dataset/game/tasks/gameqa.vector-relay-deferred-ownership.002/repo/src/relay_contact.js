(function (global) {
  "use strict";

  function ContactBook() {
    this.active = Object.create(null);
    this.accepted = Object.create(null);
  }

  ContactBook.prototype.open = function (slot) {
    return { slot: slot, series: 0 };
  };

  ContactBook.prototype.claim = function (body, target) {
    var current = this.active[target.id];
    var ticket = body.slot + ":" + body.series;
    if (current === ticket) return { accepted: false, ticket: ticket };

    this.active[target.id] = ticket;
    if (this.accepted[target.id] === ticket) {
      return { accepted: false, ticket: ticket };
    }
    this.accepted[target.id] = ticket;
    return { accepted: true, ticket: ticket };
  };

  ContactBook.prototype.separate = function (body, target) {
    var ticket = body.slot + ":" + body.series;
    if (this.active[target.id] !== ticket) return;
    delete this.active[target.id];
    body.series += 1;
  };

  ContactBook.prototype.clear = function () {
    this.active = Object.create(null);
    this.accepted = Object.create(null);
  };

  global.RelayContact = { ContactBook: ContactBook };
}(window));
