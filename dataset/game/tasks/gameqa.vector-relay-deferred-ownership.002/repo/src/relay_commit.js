(function (global) {
  "use strict";

  function RelayLane(delaySeconds) {
    this.delay = delaySeconds;
    this.nextOwner = 0;
    this.nextEntry = 0;
    this.pending = [];
    this.dropped = 0;
  }

  RelayLane.prototype.reset = function () {
    this.nextOwner = 0;
    this.nextEntry = 0;
    this.pending.length = 0;
    this.dropped = 0;
  };

  RelayLane.prototype.open = function (port) {
    this.nextOwner += 1;
    return { key: "lane-" + this.nextOwner, port: port };
  };

  RelayLane.prototype.defer = function (ticket, phase, owner, now) {
    this.nextEntry += 1;
    var entry = {
      id: this.nextEntry,
      ticket: ticket,
      phase: phase,
      owner: owner.key,
      port: owner.port,
      due: now + this.delay
    };
    this.pending.push(entry);
    return entry.id;
  };

  RelayLane.prototype.take = function (now, owner) {
    while (this.pending.length && this.pending[0].due <= now) {
      var entry = this.pending.shift();
      if (owner && entry.owner === owner.key) return entry;
      this.dropped += 1;
    }
    return null;
  };

  RelayLane.prototype.snapshot = function () {
    return {
      pending: this.pending.length,
      dropped: this.dropped,
      nextDue: this.pending.length ? this.pending[0].due : null
    };
  };

  global.RelayCommit = { RelayLane: RelayLane };
}(window));
