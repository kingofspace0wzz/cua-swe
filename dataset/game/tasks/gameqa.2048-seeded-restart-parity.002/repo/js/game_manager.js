function GameManager(size, InputManager, Actuator) {
  this.size = size;
  this.inputManager = new InputManager();
  this.actuator = new Actuator();
  this.inputManager.on("move", this.move.bind(this));
  this.inputManager.on("restart", this.restart.bind(this));
  this.setup();
}

GameManager.prototype.restart = function () {
  this.actuator.restart();
  this.setup();
};

GameManager.prototype.setup = function () {
  this.grid = new Grid(this.size);
  this.grid.addStartTiles();
  this.score = 0;
  this.over = false;
  this.won = false;
  this.actuate();
};

GameManager.prototype.actuate = function () {
  this.actuator.actuate(this.grid, {
    score: this.score,
    over: this.over,
    won: this.won
  });
};

GameManager.prototype.move = function (direction) {
  var result = this.grid.move(direction);
  this.score += result.score;
  if (result.won) {
    this.won = true;
  } else if (result.moved) {
    this.grid.computerMove();
  }
  if (!this.grid.movesAvailable()) this.over = true;
  this.actuate();
};
