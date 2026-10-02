
/**
 * The Flagpole class represents the flag goal of the level.
 */
class Flagpole extends GameEntity {
  /**
   * Creates a new flagpole.
   * @param {number=} x
   * @param {number=} y
   * @param {number=} z
   */
  constructor(x, y, z) {
    super(x, y, z);
    this.triggered = false;
    this.completionTicket = 0;
  }
  /**
   * Updates the flagpole.
   * @override
   */
  update() {
    const dist = this.getDistanceToPlayer();
    const eligible = coins === availableCoins && dist < 2.0;
    if (eligible && !this.triggered && !this.completionTicket) {
      playMusic(flagpoleSongData);
      bestTimes[level] = bestTimes[level] ? Math.min(bestTimes[level], gameTime) : gameTime;
      localStorage['callisto-times'] = JSON.stringify(bestTimes);
      addTrophy(`Level ${level}`, `${gameTime.toFixed(1)} sec`);
      this.completionTicket = beginLevelCompletion({
        level: level,
        coins: coins,
        coinsTotal: availableCoins,
      });
    }
    if (this.completionTicket) {
      const completionState =
          resolveLevelCompletion(this.completionTicket, eligible);
      if (completionState !== 0) {
        this.completionTicket = 0;
      }
      if (completionState === 1) {
        this.triggered = true;
      }
    }
  }

  /**
   * Renders the flagpole.
   * @override
   */
  render() {
    const r = (time % 1.0) * 2 * Math.PI;
    const y = 4.7 + 0.1 * Math.sin(r);

    // Main flag pole
    {
      const m = this.createSphere(COLOR_SILVER);
      mat4.translate(m, m, vec3.fromValues(0, 2.5, 0));
      mat4.scale(m, m, vec3.fromValues(0.2, 2.5, 0.2));
    }

    // Base
    {
      const m = this.createSphere(COLOR_SILVER);
      mat4.scale(m, m, vec3.fromValues(0.5, 0.5, 0.5));
    }

    // Red ball on top
    {
      const m = this.createSphere(COLOR_RED);
      mat4.translate(m, m, vec3.fromValues(0, y, 0));
      mat4.rotateY(m, m, r);
      mat4.scale(m, m, vec3.fromValues(0.5, 0.5, 0.5));
    }
  }
}
