import { Client, Logger, Tools } from 'shardy';
import { EXIT, ROUND, TURN } from './consts';

/**
 * Field side size
 */
const ROW_MAX_COUNT = 3;

/**
 * Type of play item
 *
 * @enum {number}
 */
enum ItemType {
  Cross,
  Circle,
  None,
}

/**
 * Main game class
 *
 * @export
 * @class Game
 * @typedef {Game}
 */
export class Game {
  /**
   * Current game id
   *
   * @public
   * @type {string}
   */
  public Id: string = '';

  /**
   * Current game logger instance
   *
   * @private
   * @type {Logger}
   */
  private log: Logger;

  /**
   * Game score
   *
   * @private
   * @type {number[]}
   */
  private score: number[];

  /**
   * Turn player id
   *
   * @private
   * @type {number}
   */
  private turnId: number;

  /**
   * Field data
   *
   * @private
   * @type {ItemType[][]}
   */
  private field!: ItemType[][];

  /**
   * Step counter
   *
   * @private
   * @type {number}
   */
  private count: number = 0;

  /**
   * Creates an instance of Game
   *
   * @constructor
   * @param {Client[]} players Players clients list
   */
  constructor(private players: Client[]) {
    this.turnId = Math.random() >= 0.5 ? 1 : 0;
    this.Id = Tools.generateId(10);
    this.log = new Logger(['game', this.Id]);
    this.log.info(`created`);
    this.score = [0, 0];
    this.clear();
  }

  /**
   * Exit from game
   *
   * @param {number} player Player index
   */
  exit(player: number): void {
    const index = player === 0 ? 1 : 0;
    this.players[index].command(EXIT);
    this.players.splice(player, 1);
  }

  /**
   * Clear field for next round
   */
  clear(): void {
    this.count = 0;
    this.field = [];
    for (let i = 0; i < ROW_MAX_COUNT; i++) {
      this.field[i] = [];
      for (let j = 0; j < ROW_MAX_COUNT; j++) {
        this.field[i][j] = ItemType.None;
      }
    }
  }

  /**
   * Send 'round' command
   */
  round(): void {
    const data = { g: this.Id, s: this.score, t: this.turnId, p: 0 };
    data.g = this.Id;
    data.s = this.score;
    data.t = this.turnId;
    for (let i = 0; i < this.players.length; i++) {
      data.p = i;
      this.players[i].command(ROUND, Buffer.from(JSON.stringify(data)));
    }
  }

  /**
   * Make turn and broadcast for players
   *
   * @param {number} player Player who made step
   * @param {number} x X coord
   * @param {number} y Y coord
   */
  turn(player: number, x: number, y: number): void {
    this.log.info(`turn by player: ${player}, x: ${x}, y: ${y}`);
    if (this.field[x][y] !== ItemType.None) {
      this.log.warn(`this place already played`);
      return;
    }
    if (this.turnId !== player) {
      this.log.warn(`not player turn`);
      return;
    }
    this.field[x][y] = player;
    const data = { t: this.turnId, x, y };
    this.players.forEach((item) => {
      item.command(TURN, Buffer.from(JSON.stringify(data)));
    });
    this.turnId = player === 0 ? 1 : 0;
    this.count++;
    this.checkGameOver(player, x, y);
  }

  /**
   * Check game over for this step
   *
   * @param {number} player Player who made step
   * @param {number} x X coord
   * @param {number} y Y coord
   */
  checkGameOver(player: number, x: number, y: number): void {
    this.log.info(`check game over for: ${player}`);
    let row = 0;
    let column = 0;
    let diagonal = 0;
    let diagonal2 = 0;
    for (let i = 0; i < ROW_MAX_COUNT; i++) {
      if (this.field[i][y] === player) {
        row++;
      }
      if (this.field[x][i] === player) {
        column++;
      }
      if (this.field[i][i] === player) {
        diagonal++;
      }
      if (this.field[i][ROW_MAX_COUNT - i + 1] === player) {
        diagonal2++;
      }
    }
    for (let i = 0; i < ROW_MAX_COUNT; i++) {
      this.log.info(this.field[i].toString());
    }
    this.log.info(`row: ${row}, column: ${column}, diagonal: ${diagonal}, diagonal2: ${diagonal2}`);
    if (row === ROW_MAX_COUNT || column === ROW_MAX_COUNT || diagonal === ROW_MAX_COUNT || diagonal2 === ROW_MAX_COUNT) {
      this.turnId = player;
      this.score[player]++;
      this.clear();
      this.round();
    } else if (this.count === Math.pow(ROW_MAX_COUNT, 2) - 1) {
      this.turnId = player;
      this.clear();
      this.round();
    }
  }
}
