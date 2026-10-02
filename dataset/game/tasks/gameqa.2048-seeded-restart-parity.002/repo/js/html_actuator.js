function HTMLActuator() {
  this.tileContainer = document.getElementsByClassName("tile-container")[0];
  this.scoreContainer = document.getElementsByClassName("score-container")[0];
  this.messageContainer = document.getElementsByClassName("game-message")[0];
  this.score = 0;
}

HTMLActuator.prototype.actuate = function (grid, metadata) {
  var self = this;
  window.requestAnimationFrame(function () {
    self.clearContainer(self.tileContainer);
    grid.cells.forEach(function (column) {
      column.forEach(function (tile) {
        if (tile) {
          self.addTile(tile);
        }
      });
    });
    self.updateScore(metadata.score);
    if (metadata.over) {
      self.message(false);
    }
    if (metadata.won) {
      self.message(true);
    }
  });
};

HTMLActuator.prototype.restart = function () {
  this.clearMessage();
};

HTMLActuator.prototype.clearContainer = function (container) {
  if (!container) {
    return;
  }
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
};

HTMLActuator.prototype.addTile = function (tile) {
  var self = this;
  var element = document.createElement("div");
  var previousPosition = tile.previousPosition || { x: tile.x, y: tile.y };
  var positionClass = this.positionClass(previousPosition);
  var classes = ["tile", "tile-" + tile.value, positionClass];

  this.applyClasses(element, classes);
  element.textContent = tile.value;

  if (tile.previousPosition) {
    window.requestAnimationFrame(function () {
      classes[2] = self.positionClass({ x: tile.x, y: tile.y });
      self.applyClasses(element, classes);
    });
  } else if (tile.mergedFrom) {
    classes.push("tile-merged");
    this.applyClasses(element, classes);
    tile.mergedFrom.forEach(function (mergedTile) {
      self.addTile(mergedTile);
    });
  } else {
    classes.push("tile-new");
    this.applyClasses(element, classes);
  }

  this.tileContainer.appendChild(element);
};

HTMLActuator.prototype.applyClasses = function (element, classes) {
  element.setAttribute("class", classes.join(" "));
};

HTMLActuator.prototype.normalizePosition = function (position) {
  return { x: position.x + 1, y: position.y + 1 };
};

HTMLActuator.prototype.positionClass = function (position) {
  position = this.normalizePosition(position);
  return "tile-position-" + position.x + "-" + position.y;
};

HTMLActuator.prototype.updateScore = function (score) {
  this.clearContainer(this.scoreContainer);
  var difference = score - this.score;
  this.score = score;
  this.scoreContainer.textContent = this.score;
  if (difference > 0) {
    var addition = document.createElement("div");
    addition.classList.add("score-addition");
    addition.textContent = "+" + difference;
    this.scoreContainer.appendChild(addition);
  }
};

HTMLActuator.prototype.message = function (won) {
  var className = won ? "game-won" : "game-over";
  var text = won ? "You win!" : "Game over!";
  this.messageContainer.classList.add(className);
  this.messageContainer.getElementsByTagName("p")[0].textContent = text;
};

HTMLActuator.prototype.clearMessage = function () {
  this.messageContainer.classList.remove("game-won", "game-over");
};

HTMLActuator.prototype.showHint = function (index) {
  document.getElementById("feedback-container").innerHTML = ["↑", "→", "↓", "←"][index];
};

HTMLActuator.prototype.setRunButton = function (label) {
  document.getElementById("run-button").innerHTML = label;
};
